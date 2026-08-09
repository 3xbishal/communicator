(function () {
  let mediaRecorder = null;
  let chunks = [];
  let activeStream = null;

  function isSupported() {
    return !!(navigator.mediaDevices && window.MediaRecorder);
  }

  function start(onStop) {
    if (!isSupported()) {
      alert('Voice notes need microphone support, which this browser does not provide.');
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      activeStream = stream;
      chunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = function (e) {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };
      mediaRecorder.onstop = function () {
        const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
        activeStream.getTracks().forEach(function (t) { t.stop(); });
        onStop(blob);
      };
      mediaRecorder.start();
    }).catch(function () {
      alert('Microphone access was denied or is unavailable.');
    });
  }

  function stop() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
  }

  window.CommunicatorRecorder = { start: start, stop: stop, isSupported: isSupported };
})();
