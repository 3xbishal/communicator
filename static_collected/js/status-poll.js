(function ($) {
  var POLL_INTERVAL_MS = 4000;

  function poll() {
    if (document.hidden) {
      setTimeout(poll, POLL_INTERVAL_MS);
      return;
    }
    $.get('/status/poll/')
      .done(function (data) {
        if (data.status && data.status !== 'pending') {
          // Approved or rejected: let the server decide where to route —
          // a plain reload re-runs identity.views.status()'s own logic.
          window.location.reload();
          return;
        }
        setTimeout(poll, POLL_INTERVAL_MS);
      })
      .fail(function () {
        setTimeout(poll, POLL_INTERVAL_MS * 2);
      });
  }

  setTimeout(poll, POLL_INTERVAL_MS);
})(jQuery);
