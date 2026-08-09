(function () {
  const POLL_INTERVAL_MS = 3500;
  const MAX_INTERVAL_MS = 30000;
  let currentInterval = POLL_INTERVAL_MS;
  let timer = null;
  const dismissedCallIds = new Set();

  function schedule(delay) {
    clearTimeout(timer);
    timer = setTimeout(poll, delay);
  }

  function updateUnreadBadge(count) {
    const el = document.getElementById('unread-badge');
    if (!el) return;
    if (count > 0) {
      el.textContent = count > 99 ? '99+' : String(count);
      el.classList.remove('hidden');
    } else {
      el.classList.add('hidden');
    }
  }

  function poll() {
    if (document.hidden) {
      schedule(currentInterval);
      return;
    }
    apiFetch('/chat/events/')
      .then(function (resp) {
        if (!resp.ok) throw new Error('events poll failed: ' + resp.status);
        return resp.json();
      })
      .then(function (data) {
        currentInterval = POLL_INTERVAL_MS;
        updateUnreadBadge(data.unread_total);
        if (data.incoming_call && !dismissedCallIds.has(data.incoming_call.call_id)) {
          window.CommunicatorCall.showIncoming(data.incoming_call);
        }
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

  window.CommunicatorGlobalPoll = {
    markCallHandled: function (id) { dismissedCallIds.add(id); },
  };

  poll();
})();
