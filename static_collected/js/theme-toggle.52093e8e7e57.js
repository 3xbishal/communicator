(function ($) {
  var $root = $(document.documentElement);
  var $icon = $('#theme-icon');

  function currentTheme() {
    return $root.attr('data-bs-theme') === 'dark' ? 'dark' : 'light';
  }

  function reflectIcon() {
    var dark = currentTheme() === 'dark';
    // Icon shows the mode a click will switch TO, matching the common
    // sun/moon toggle convention (moon visible in light mode, sun in dark).
    $icon.toggleClass('fa-moon', !dark).toggleClass('fa-sun', dark);
  }

  $('#theme-toggle').on('click', function () {
    var next = currentTheme() === 'dark' ? 'light' : 'dark';
    $root.attr('data-bs-theme', next);
    localStorage.setItem('theme', next);
    reflectIcon();
  });

  reflectIcon();
})(jQuery);
