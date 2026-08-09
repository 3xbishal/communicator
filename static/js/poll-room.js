(function ($) {
  var $shell = $('.room-shell');
  if (!$shell.length) return;

  var lastId = parseInt($shell.data('last-id') || 0, 10);
  var currentDay = String($shell.data('today') || '');
  var $messageList = $('#message-list');
  var $membersList = $('#members-list');
  var $composer = $('#composer');
  var $textInput = $('#text-input');
  var $fileInput = $('#file-input');
  var $fileLabel = $fileInput.closest('label');
  var $folderInput = $('#folder-input');
  var $folderLabel = $folderInput.closest('label');
  var $micBtn = $('#mic-btn');
  var $uploadStatus = $('#upload-status');
  var $uploadFilename = $('#upload-filename');
  var $uploadPercent = $('#upload-percent');
  var $uploadProgressBar = $('#upload-progress-bar');

  var initialMessages = [];
  var $initialData = $('#initial-messages');
  if ($initialData.length) {
    initialMessages = JSON.parse($initialData.text());
  }

  function fmtTime(iso) {
    var d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function humanSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function avatarSpan(username, color) {
    return $('<span>')
      .addClass('avatar avatar-inline')
      .css('background', color)
      .text((username || '?').charAt(0).toUpperCase());
  }

  function bubbleForMessage(msg) {
    var $bubble = $('<div>').addClass('bubble ' + (msg.mine ? 'mine' : 'theirs bg-body-tertiary'));

    if (!msg.mine) {
      var $sender = $('<span>').addClass('bubble-sender');
      $sender.append(avatarSpan(msg.sender, msg.color));
      $sender.append(document.createTextNode(msg.sender));
      $bubble.append($sender);
    }

    if (msg.kind === 'text') {
      $bubble.append($('<p>').addClass('bubble-text').text(msg.text));
    } else if (msg.kind === 'voice') {
      $bubble.append($('<audio>').attr({ controls: true, src: msg.attachment_url }));
    } else if (msg.kind === 'file') {
      var $link = $('<a>')
        .attr({ href: msg.attachment_url, target: '_blank', rel: 'noopener' })
        .text((msg.original_filename || 'File') + ' (' + humanSize(msg.size) + ')');
      $bubble.append($link);
      if (msg.text) {
        $bubble.append($('<p>').addClass('bubble-text').text(msg.text));
      }
    }

    $bubble.append($('<span>').addClass('bubble-time').text(fmtTime(msg.created_at)));
    return $bubble;
  }

  function appendMessage(msg) {
    $messageList.append(bubbleForMessage(msg));
    $messageList.scrollTop($messageList.prop('scrollHeight'));
  }

  function renderMembers(members) {
    $membersList.empty();
    members.forEach(function (m) {
      var $li = $('<li>').addClass('member-row' + (m.mine ? ' mine' : ''));
      $li.append(avatarSpan(m.username, m.color));
      $li.append($('<span>').addClass('member-name').text(m.username + (m.mine ? ' (you)' : '')));
      $li.append($('<span>').addClass('presence-dot' + (m.online ? ' online' : '')));
      $membersList.append($li);
    });
  }

  // --- Polling ---
  var POLL_INTERVAL_MS = 3000;
  var MAX_INTERVAL_MS = 20000;
  var currentInterval = POLL_INTERVAL_MS;
  var pollTimer = null;

  function schedule(delay) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, delay);
  }

  function poll() {
    if (document.hidden) {
      schedule(currentInterval);
      return;
    }
    $.get('/chat/messages/', { after: lastId })
      .done(function (data) {
        // The server recomputes "today" on every poll. If it no longer
        // matches the day this page loaded with, midnight has passed
        // while the tab sat open — reload into a fresh live chat instead
        // of silently appending today's messages under yesterday's.
        if (currentDay && data.today && data.today !== currentDay) {
          window.location.reload();
          return;
        }
        currentInterval = POLL_INTERVAL_MS;
        data.messages.forEach(function (msg) {
          lastId = Math.max(lastId, msg.id);
          appendMessage(msg);
        });
        renderMembers(data.members);
        schedule(currentInterval);
      })
      .fail(function (xhr) {
        if (xhr.status === 403) {
          window.location.reload();
          return;
        }
        currentInterval = Math.min(currentInterval * 2, MAX_INTERVAL_MS);
        schedule(currentInterval);
      });
  }

  $(document).on('visibilitychange', function () {
    if (!document.hidden) {
      currentInterval = POLL_INTERVAL_MS;
      schedule(200);
    }
  });

  // --- Upload progress ---
  var uploading = false;

  function setUploadingControlsDisabled(disabled) {
    uploading = disabled;
    $fileInput.prop('disabled', disabled);
    $fileLabel.toggleClass('disabled', disabled).attr('aria-disabled', disabled ? 'true' : null);
    $folderInput.prop('disabled', disabled);
    $folderLabel.toggleClass('disabled', disabled).attr('aria-disabled', disabled ? 'true' : null);
    $micBtn.prop('disabled', disabled);
  }

  // The server always replies with a specific reason (blocked extension,
  // size limit, rate limit...) — surface it instead of a generic alert,
  // otherwise "why didn't this send" is invisible to the user.
  function errorMessage(xhr) {
    var data = xhr && xhr.responseJSON;
    if (data && data.error) {
      return data.error === 'rate_limited'
        ? "You're sending too fast — wait a moment and try again."
        : data.error;
    }
    return xhr && xhr.status ? 'Server error (' + xhr.status + ').' : 'Network error.';
  }

  function showUploadProgress(filename) {
    $uploadFilename.text('Uploading ' + filename + '...');
    $uploadPercent.text('0%');
    $uploadProgressBar.css('width', '0%').attr('aria-valuenow', 0);
    $uploadStatus.removeClass('d-none');
  }

  function updateUploadProgress(percent) {
    $uploadPercent.text(percent + '%');
    $uploadProgressBar.css('width', percent + '%').attr('aria-valuenow', percent);
  }

  function hideUploadProgress() {
    $uploadStatus.addClass('d-none');
  }

  // --- Composer ---
  function postAttachment(formData, onProgress) {
    return $.ajax({
      url: '/chat/send/',
      method: 'POST',
      data: formData,
      processData: false,
      contentType: false,
      // Belt-and-suspenders: csrf.js's global $.ajaxSetup(beforeSend...)
      // already attaches this, but setting it explicitly here too means
      // the one truly critical write in the app (sending a message)
      // doesn't silently depend on load order or a stale cached csrf.js
      // from before it existed.
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      xhr: function () {
        var xhr = $.ajaxSettings.xhr();
        if (onProgress && xhr.upload) {
          xhr.upload.addEventListener('progress', function (e) {
            if (e.lengthComputable) {
              onProgress(Math.round((e.loaded / e.total) * 100));
            }
          });
        }
        return xhr;
      },
    }).done(function (msg) {
      lastId = Math.max(lastId, msg.id);
      appendMessage(msg);
    });
  }

  function sendPayload(formData, progressLabel) {
    var showsProgress = !!progressLabel;
    if (showsProgress) {
      setUploadingControlsDisabled(true);
      showUploadProgress(progressLabel);
    }

    return postAttachment(formData, showsProgress ? updateUploadProgress : null).always(function () {
      if (showsProgress) {
        updateUploadProgress(100);
        setTimeout(hideUploadProgress, 300);
        setUploadingControlsDisabled(false);
      }
    });
  }

  // Sends a folder's/multi-select's files one at a time — each Message
  // holds exactly one attachment, so "uploading a folder" means one
  // message per file, sequenced so they don't fight over the progress bar
  // or the rate limiter. A file rejected (too large, blocked type, ...)
  // doesn't stop the rest of the batch; failures are reported together
  // at the end with the server's actual reason for each.
  function sendFilesSequentially(fileList) {
    var files = Array.prototype.slice.call(fileList);
    if (!files.length) return;
    var total = files.length;
    var failures = [];

    setUploadingControlsDisabled(true);

    function sendNext(i) {
      if (i >= total) {
        updateUploadProgress(100);
        setTimeout(hideUploadProgress, 300);
        setUploadingControlsDisabled(false);
        if (failures.length) {
          alert('Some files failed to send:\n' + failures.join('\n'));
        }
        return;
      }

      var file = files[i];
      var label = total > 1 ? file.name + ' (' + (i + 1) + '/' + total + ')' : file.name;
      showUploadProgress(label);

      var formData = new FormData();
      formData.append('attachment', file);
      formData.append('kind', 'file');

      postAttachment(formData, updateUploadProgress)
        .fail(function (xhr) {
          failures.push(file.name + ': ' + errorMessage(xhr));
        })
        .always(function () {
          sendNext(i + 1);
        });
    }

    sendNext(0);
  }

  $composer.on('submit', function (e) {
    e.preventDefault();
    var text = $textInput.val().trim();
    if (!text) return;
    var formData = new FormData();
    formData.append('text', text);
    $textInput.val('');
    sendPayload(formData).fail(function (xhr) {
      $textInput.val(text);
      alert('Message failed to send: ' + errorMessage(xhr));
    });
  });

  $fileInput.on('change', function () {
    if (uploading || !this.files.length) return;
    sendFilesSequentially(this.files);
    this.value = '';
  });

  $folderInput.on('change', function () {
    if (uploading || !this.files.length) return;
    sendFilesSequentially(this.files);
    this.value = '';
  });

  // --- Drag & drop ---
  // Recursively walks a dropped entry (file or directory) into a flat list
  // of Files, using the same webkitGetAsEntry traversal Chrome/Firefox/Edge
  // expose for dropped folders. Falls back to dataTransfer.files (no
  // recursion) on browsers without it.
  function filesFromEntry(entry) {
    return new Promise(function (resolve) {
      if (!entry) {
        resolve([]);
      } else if (entry.isFile) {
        entry.file(function (file) { resolve([file]); }, function () { resolve([]); });
      } else if (entry.isDirectory) {
        var reader = entry.createReader();
        var collected = [];
        (function readBatch() {
          reader.readEntries(function (entries) {
            if (!entries.length) {
              Promise.all(collected).then(function (groups) {
                resolve(Array.prototype.concat.apply([], groups));
              });
              return;
            }
            entries.forEach(function (child) { collected.push(filesFromEntry(child)); });
            readBatch();
          }, function () { resolve([]); });
        })();
      } else {
        resolve([]);
      }
    });
  }

  function filesFromDataTransfer(dataTransfer) {
    var items = dataTransfer.items;
    if (items && items.length && items[0].webkitGetAsEntry) {
      var entries = Array.prototype.map.call(items, function (item) {
        return item.webkitGetAsEntry && item.webkitGetAsEntry();
      }).filter(Boolean);
      if (entries.length) {
        return Promise.all(entries.map(filesFromEntry)).then(function (groups) {
          return Array.prototype.concat.apply([], groups);
        });
      }
    }
    return Promise.resolve(Array.prototype.slice.call(dataTransfer.files || []));
  }

  var $roomMain = $('.room-main');
  var $dropOverlay = $('.drop-overlay');
  var dragDepth = 0;

  $roomMain.on('dragenter', function (e) {
    if (uploading || !e.originalEvent.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    dragDepth++;
    $dropOverlay.removeClass('d-none');
  });

  $roomMain.on('dragover', function (e) {
    if (uploading || !e.originalEvent.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
  });

  $roomMain.on('dragleave', function (e) {
    if (uploading) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) $dropOverlay.addClass('d-none');
  });

  $roomMain.on('drop', function (e) {
    dragDepth = 0;
    $dropOverlay.addClass('d-none');
    if (uploading) return;
    var dt = e.originalEvent.dataTransfer;
    if (!dt || !dt.types.includes('Files')) return;
    e.preventDefault();
    filesFromDataTransfer(dt).then(function (files) {
      if (files.length) sendFilesSequentially(files);
    });
  });

  var recording = false;
  $micBtn.on('click', function () {
    if (uploading) return;
    if (!window.CommunicatorRecorder.isSupported()) {
      alert('Voice notes need microphone support, which this browser does not provide.');
      return;
    }
    if (!recording) {
      recording = true;
      $micBtn.addClass('recording').attr('title', 'Recording — click to stop');
      window.CommunicatorRecorder.start(function (blob) {
        $micBtn.removeClass('recording').attr('title', 'Record a voice note');
        recording = false;
        var formData = new FormData();
        formData.append('attachment', blob, 'voice-note.webm');
        formData.append('kind', 'voice');
        sendPayload(formData, 'voice note').fail(function (xhr) {
          alert('Voice note failed to send: ' + errorMessage(xhr));
        });
      });
    } else {
      window.CommunicatorRecorder.stop();
    }
  });

  initialMessages.forEach(appendMessage);
  poll();
})(jQuery);
