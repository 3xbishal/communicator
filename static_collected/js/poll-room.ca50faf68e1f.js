(function ($) {
  var $shell = $('.room-shell');
  if (!$shell.length) return;

  var lastId = parseInt($shell.data('last-id') || 0, 10);
  var $messageList = $('#message-list');
  var $membersList = $('#members-list');
  var $composer = $('#composer');
  var $textInput = $('#text-input');
  var $fileInput = $('#file-input');
  var $micBtn = $('#mic-btn');

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

  // --- Composer ---
  function sendPayload(formData) {
    return $.ajax({
      url: '/chat/send/',
      method: 'POST',
      data: formData,
      processData: false,
      contentType: false,
    }).done(function (msg) {
      lastId = Math.max(lastId, msg.id);
      appendMessage(msg);
    });
  }

  $composer.on('submit', function (e) {
    e.preventDefault();
    var text = $textInput.val().trim();
    if (!text) return;
    var formData = new FormData();
    formData.append('text', text);
    $textInput.val('');
    sendPayload(formData).fail(function () {
      $textInput.val(text);
      alert('Message failed to send.');
    });
  });

  $fileInput.on('change', function () {
    if (!this.files.length) return;
    var formData = new FormData();
    formData.append('attachment', this.files[0]);
    formData.append('kind', 'file');
    sendPayload(formData)
      .fail(function () {
        alert('File failed to send.');
      })
      .always(function () {
        $fileInput.val('');
      });
  });

  var recording = false;
  $micBtn.on('click', function () {
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
        sendPayload(formData).fail(function () {
          alert('Voice note failed to send.');
        });
      });
    } else {
      window.CommunicatorRecorder.stop();
    }
  });

  initialMessages.forEach(appendMessage);
  poll();
})(jQuery);
