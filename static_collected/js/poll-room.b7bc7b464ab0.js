(function () {
  const page = document.querySelector('.room-page');
  if (!page) return;

  let lastId = parseInt(page.dataset.lastId || '0', 10);
  const messageList = document.getElementById('message-list');
  const membersList = document.getElementById('members-list');
  const composer = document.getElementById('composer');
  const textInput = document.getElementById('text-input');
  const fileInput = document.getElementById('file-input');
  const micBtn = document.getElementById('mic-btn');

  const initialDataEl = document.getElementById('initial-messages');
  const initialMessages = initialDataEl ? JSON.parse(initialDataEl.textContent) : [];

  function fmtTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function humanSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function avatarSpan(username, color) {
    const avatar = document.createElement('span');
    avatar.className = 'avatar avatar-inline';
    avatar.style.background = color;
    avatar.textContent = (username || '?').charAt(0).toUpperCase();
    return avatar;
  }

  function bubbleForMessage(msg) {
    const div = document.createElement('div');
    div.className = 'bubble ' + (msg.mine ? 'mine' : 'theirs');

    if (!msg.mine) {
      const sender = document.createElement('span');
      sender.className = 'bubble-sender';
      sender.appendChild(avatarSpan(msg.sender, msg.color));
      sender.appendChild(document.createTextNode(msg.sender));
      div.appendChild(sender);
    }

    if (msg.kind === 'text') {
      const p = document.createElement('p');
      p.className = 'bubble-text';
      p.textContent = msg.text;
      div.appendChild(p);
    } else if (msg.kind === 'voice') {
      const audio = document.createElement('audio');
      audio.controls = true;
      audio.src = msg.attachment_url;
      div.appendChild(audio);
    } else if (msg.kind === 'file') {
      const link = document.createElement('a');
      link.href = msg.attachment_url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = (msg.original_filename || 'File') + ' (' + humanSize(msg.size) + ')';
      div.appendChild(link);
      if (msg.text) {
        const p = document.createElement('p');
        p.className = 'bubble-text';
        p.textContent = msg.text;
        div.appendChild(p);
      }
    }

    const time = document.createElement('span');
    time.className = 'bubble-time';
    time.textContent = fmtTime(msg.created_at);
    div.appendChild(time);
    return div;
  }

  function appendMessage(msg) {
    messageList.appendChild(bubbleForMessage(msg));
    messageList.scrollTop = messageList.scrollHeight;
  }

  function renderMembers(members) {
    membersList.innerHTML = '';
    members.forEach(function (m) {
      const li = document.createElement('li');
      li.className = 'member-row' + (m.mine ? ' mine' : '');
      li.appendChild(avatarSpan(m.username, m.color));
      const name = document.createElement('span');
      name.className = 'member-name';
      name.textContent = m.username + (m.mine ? ' (you)' : '');
      li.appendChild(name);
      const dot = document.createElement('span');
      dot.className = 'presence-dot' + (m.online ? ' online' : '');
      li.appendChild(dot);
      membersList.appendChild(li);
    });
  }

  // --- Polling ---
  const POLL_INTERVAL_MS = 3000;
  const MAX_INTERVAL_MS = 20000;
  let currentInterval = POLL_INTERVAL_MS;
  let pollTimer = null;

  function schedule(delay) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, delay);
  }

  function poll() {
    if (document.hidden) {
      schedule(currentInterval);
      return;
    }
    apiFetch('/chat/messages/?after=' + lastId)
      .then(function (r) {
        if (r.status === 403) {
          window.location.reload();
          throw new Error('no longer approved');
        }
        if (!r.ok) throw new Error('poll failed');
        return r.json();
      })
      .then(function (data) {
        currentInterval = POLL_INTERVAL_MS;
        data.messages.forEach(function (msg) {
          lastId = Math.max(lastId, msg.id);
          appendMessage(msg);
        });
        renderMembers(data.members);
        schedule(currentInterval);
      })
      .catch(function () {
        currentInterval = Math.min(currentInterval * 2, MAX_INTERVAL_MS);
        schedule(currentInterval);
      });
  }

  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) {
      currentInterval = POLL_INTERVAL_MS;
      schedule(200);
    }
  });

  // --- Composer ---
  function sendPayload(formData) {
    return apiFetch('/chat/send/', { method: 'POST', body: formData })
      .then(function (r) { if (!r.ok) throw new Error('send failed'); return r.json(); })
      .then(function (msg) {
        lastId = Math.max(lastId, msg.id);
        appendMessage(msg);
      });
  }

  composer.addEventListener('submit', function (e) {
    e.preventDefault();
    const text = textInput.value.trim();
    if (!text) return;
    const formData = new FormData();
    formData.append('text', text);
    textInput.value = '';
    sendPayload(formData).catch(function () {
      textInput.value = text;
      alert('Message failed to send.');
    });
  });

  fileInput.addEventListener('change', function () {
    if (!fileInput.files.length) return;
    const formData = new FormData();
    formData.append('attachment', fileInput.files[0]);
    formData.append('kind', 'file');
    sendPayload(formData)
      .catch(function () { alert('File failed to send.'); })
      .finally(function () { fileInput.value = ''; });
  });

  let recording = false;
  micBtn.addEventListener('click', function () {
    if (!window.CommunicatorRecorder.isSupported()) {
      alert('Voice notes need microphone support, which this browser does not provide.');
      return;
    }
    if (!recording) {
      recording = true;
      micBtn.classList.add('recording');
      micBtn.textContent = 'Stop';
      window.CommunicatorRecorder.start(function (blob) {
        micBtn.classList.remove('recording');
        micBtn.textContent = 'Mic';
        recording = false;
        const formData = new FormData();
        formData.append('attachment', blob, 'voice-note.webm');
        formData.append('kind', 'voice');
        sendPayload(formData).catch(function () { alert('Voice note failed to send.'); });
      });
    } else {
      window.CommunicatorRecorder.stop();
    }
  });

  initialMessages.forEach(appendMessage);
  poll();
})();
