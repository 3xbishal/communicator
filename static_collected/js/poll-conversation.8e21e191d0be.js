(function () {
  const page = document.querySelector('.chat-page');
  if (!page) return;

  const pin = page.dataset.pin;
  const baseUrl = '/chat/' + pin + '/';
  let lastId = parseInt(page.dataset.lastId || '0', 10);

  const messageList = document.getElementById('message-list');
  const composer = document.getElementById('composer');
  const textInput = document.getElementById('text-input');
  const fileInput = document.getElementById('file-input');
  const callBtn = document.getElementById('call-btn');
  const callPanel = document.getElementById('call-panel');
  const callPanelText = document.getElementById('call-panel-text');
  const callAcceptBtn = document.getElementById('call-accept-btn');
  const callEndBtn = document.getElementById('call-end-btn');
  const pttArea = document.getElementById('ptt-area');
  const pttBtn = document.getElementById('ptt-btn');
  const chatStatus = document.getElementById('chat-status');

  const initialDataEl = document.getElementById('initial-messages');
  const initialMessages = initialDataEl ? JSON.parse(initialDataEl.textContent) : [];

  let activeCall = null; // {callId, direction: 'outgoing'|'incoming', status: 'ringing'|'accepted'}

  function fmtTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function humanSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function callLabel(msg) {
    switch (msg.kind) {
      case 'call_ring': return msg.mine ? 'Outgoing call' : 'Incoming call';
      case 'call_accept': return 'Call accepted';
      case 'call_decline': return 'Call declined';
      case 'call_end': return 'Call ended';
      case 'call_missed': return msg.mine ? 'No answer' : 'Missed call';
      default: return '';
    }
  }

  function bubbleForMessage(msg) {
    if (msg.kind.indexOf('call_') === 0) {
      const sys = document.createElement('div');
      sys.className = 'system-bubble';
      sys.textContent = callLabel(msg) + ' · ' + fmtTime(msg.created_at);
      return sys;
    }

    const div = document.createElement('div');
    div.className = 'bubble ' + (msg.mine ? 'mine' : 'theirs');

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

  function setActiveCall(state) {
    activeCall = state;
    renderCallPanel();
  }

  function clearActiveCall() {
    activeCall = null;
    renderCallPanel();
  }

  function renderCallPanel() {
    if (!activeCall) {
      callPanel.classList.add('hidden');
      pttArea.classList.add('hidden');
      callAcceptBtn.classList.add('hidden');
      return;
    }
    callPanel.classList.remove('hidden');
    if (activeCall.status === 'accepted') {
      callPanelText.textContent = 'Call connected — hold the button to talk';
      pttArea.classList.remove('hidden');
      callAcceptBtn.classList.add('hidden');
      callEndBtn.textContent = 'End';
    } else if (activeCall.direction === 'outgoing') {
      callPanelText.textContent = 'Calling…';
      pttArea.classList.add('hidden');
      callAcceptBtn.classList.add('hidden');
      callEndBtn.textContent = 'Cancel';
    } else {
      callPanelText.textContent = 'Incoming call';
      pttArea.classList.add('hidden');
      callAcceptBtn.classList.remove('hidden');
      callEndBtn.textContent = 'Decline';
    }
  }

  function deriveInitialCallState() {
    const byCallId = new Map();
    let latestRing = null;
    initialMessages.forEach(function (m) {
      if (m.kind.indexOf('call_') !== 0) return;
      if (!byCallId.has(m.call_id)) byCallId.set(m.call_id, []);
      byCallId.get(m.call_id).push(m);
      if (m.kind === 'call_ring') latestRing = m;
    });
    if (!latestRing) return;
    const related = byCallId.get(latestRing.call_id) || [];
    const resolution = related.find(function (m) { return m.kind !== 'call_ring'; });
    if (!resolution) {
      setActiveCall({ callId: latestRing.call_id, direction: latestRing.mine ? 'outgoing' : 'incoming', status: 'ringing' });
    } else if (resolution.kind === 'call_accept') {
      setActiveCall({ callId: latestRing.call_id, direction: latestRing.mine ? 'outgoing' : 'incoming', status: 'accepted' });
    }
  }

  function handleIncomingMessage(msg) {
    appendMessage(msg);
    if (msg.kind === 'call_ring') {
      setActiveCall({ callId: msg.call_id, direction: msg.mine ? 'outgoing' : 'incoming', status: 'ringing' });
    } else if (activeCall && activeCall.callId === msg.call_id) {
      if (msg.kind === 'call_accept') {
        setActiveCall(Object.assign({}, activeCall, { status: 'accepted' }));
      } else if (msg.kind === 'call_decline' || msg.kind === 'call_end' || msg.kind === 'call_missed') {
        clearActiveCall();
      }
    }
  }

  // --- Polling ---
  const POLL_INTERVAL_MS = 2500;
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
    apiFetch(baseUrl + 'messages/?after=' + lastId)
      .then(function (r) { if (!r.ok) throw new Error('poll failed'); return r.json(); })
      .then(function (data) {
        currentInterval = POLL_INTERVAL_MS;
        data.messages.forEach(function (msg) {
          lastId = Math.max(lastId, msg.id);
          handleIncomingMessage(msg);
        });
        if (chatStatus) chatStatus.textContent = data.other_online ? 'online' : 'offline';
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
    return apiFetch(baseUrl + 'send/', { method: 'POST', body: formData })
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
      .catch(function (err) { alert('File failed to send.'); })
      .finally(function () { fileInput.value = ''; });
  });

  // --- Calling ---
  callBtn.addEventListener('click', function () {
    if (activeCall) return;
    apiFetch(baseUrl + 'call/ring/', { method: 'POST' })
      .then(function (r) { if (!r.ok) throw new Error('ring failed'); return r.json(); })
      .then(function (msg) {
        lastId = Math.max(lastId, msg.id);
        appendMessage(msg);
        setActiveCall({ callId: msg.call_id, direction: 'outgoing', status: 'ringing' });
      })
      .catch(function () { alert('Could not start the call.'); });
  });

  callAcceptBtn.addEventListener('click', function () {
    if (!activeCall) return;
    apiFetch(baseUrl + 'call/' + activeCall.callId + '/accept/', { method: 'POST' })
      .then(function (r) { if (!r.ok) throw new Error('accept failed'); return r.json(); })
      .then(function (msg) {
        lastId = Math.max(lastId, msg.id);
        appendMessage(msg);
        setActiveCall(Object.assign({}, activeCall, { status: 'accepted' }));
      });
  });

  callEndBtn.addEventListener('click', function () {
    if (!activeCall) return;
    const action = activeCall.status === 'accepted' ? 'end' : (activeCall.direction === 'outgoing' ? 'end' : 'decline');
    apiFetch(baseUrl + 'call/' + activeCall.callId + '/' + action + '/', { method: 'POST' })
      .then(function (r) { if (r.ok) return r.json(); })
      .then(function (msg) {
        if (msg) {
          lastId = Math.max(lastId, msg.id);
          appendMessage(msg);
        }
        clearActiveCall();
      });
  });

  let recording = false;
  function pttDown(e) {
    e.preventDefault();
    if (recording || !activeCall || activeCall.status !== 'accepted') return;
    recording = true;
    pttBtn.classList.add('recording');
    window.CommunicatorRecorder.start(function (blob) {
      pttBtn.classList.remove('recording');
      recording = false;
      const formData = new FormData();
      formData.append('attachment', blob, 'voice-note.webm');
      formData.append('kind', 'voice');
      sendPayload(formData).catch(function () { alert('Voice note failed to send.'); });
    });
  }
  function pttUp(e) {
    e.preventDefault();
    if (!recording) return;
    window.CommunicatorRecorder.stop();
  }
  pttBtn.addEventListener('mousedown', pttDown);
  pttBtn.addEventListener('mouseup', pttUp);
  pttBtn.addEventListener('mouseleave', pttUp);
  pttBtn.addEventListener('touchstart', pttDown);
  pttBtn.addEventListener('touchend', pttUp);

  initialMessages.forEach(appendMessage);
  deriveInitialCallState();
  poll();
})();
