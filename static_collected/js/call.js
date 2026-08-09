(function () {
  let audioCtx = null;
  let ringTimer = null;
  let currentIncoming = null;

  function unlockAudio() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!audioCtx) {
      audioCtx = new Ctx();
    } else if (audioCtx.state === 'suspended') {
      audioCtx.resume().catch(function () {});
    }
  }
  // Browsers block audio until a user gesture; priming the AudioContext on
  // the first click/tap anywhere means the ringtone can actually play by
  // the time a real incoming call arrives later in the session.
  document.addEventListener('click', unlockAudio);
  document.addEventListener('touchstart', unlockAudio);

  function beep(freq, startTime, duration) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.frequency.value = freq;
    osc.type = 'sine';
    gain.gain.setValueAtTime(0.0001, startTime);
    gain.gain.exponentialRampToValueAtTime(0.2, startTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration);
  }

  function playRingPattern() {
    if (!audioCtx) return;
    const now = audioCtx.currentTime;
    try {
      beep(880, now, 0.3);
      beep(660, now + 0.35, 0.3);
    } catch (e) {
      /* audio not available; overlay is still shown visually */
    }
  }

  function startRingtone() {
    unlockAudio();
    stopRingtone();
    playRingPattern();
    ringTimer = setInterval(playRingPattern, 1500);
  }

  function stopRingtone() {
    if (ringTimer) {
      clearInterval(ringTimer);
      ringTimer = null;
    }
  }

  function showIncoming(call) {
    if (currentIncoming) return;
    currentIncoming = call;
    const overlay = document.getElementById('incoming-call-overlay');
    const nameEl = document.getElementById('incoming-call-name');
    if (!overlay) return;
    nameEl.textContent = call.from_name;
    overlay.classList.remove('hidden');
    document.title = 'Incoming call…';
    startRingtone();
  }

  function hideIncoming() {
    const overlay = document.getElementById('incoming-call-overlay');
    if (overlay) overlay.classList.add('hidden');
    stopRingtone();
    document.title = 'Communicator';
    currentIncoming = null;
  }

  function respond(action) {
    if (!currentIncoming) return;
    const call = currentIncoming;
    if (window.CommunicatorGlobalPoll) window.CommunicatorGlobalPoll.markCallHandled(call.call_id);
    hideIncoming();
    apiFetch('/chat/' + call.from_pin + '/call/' + call.call_id + '/' + action + '/', { method: 'POST' })
      .then(function () {
        if (action === 'accept') {
          window.location.href = '/chat/' + call.from_pin + '/';
        }
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    const acceptBtn = document.getElementById('incoming-call-accept');
    const declineBtn = document.getElementById('incoming-call-decline');
    if (acceptBtn) acceptBtn.addEventListener('click', function () { respond('accept'); });
    if (declineBtn) declineBtn.addEventListener('click', function () { respond('decline'); });
  });

  window.CommunicatorCall = { showIncoming: showIncoming, hideIncoming: hideIncoming };
})();
