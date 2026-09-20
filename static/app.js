// CampusConnect - small progressive enhancements. The app works without this file.
document.addEventListener('DOMContentLoaded', function () {
  // Filters: apply as soon as a dropdown changes.
  document.querySelectorAll('form[data-autosubmit] select').forEach(function (sel) {
    sel.addEventListener('change', function () { sel.form.submit(); });
  });

  // Ask before destructive actions.
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!window.confirm(form.getAttribute('data-confirm'))) e.preventDefault();
    });
  });

  // Dismiss flash messages.
  document.querySelectorAll('.flash-close').forEach(function (btn) {
    btn.addEventListener('click', function () { btn.closest('.flash').remove(); });
  });

  // Demo accounts: fill the login form.
  document.querySelectorAll('.demo-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.getElementById('email').value = btn.dataset.email;
      document.getElementById('password').value = btn.dataset.password;
      document.querySelector('#login-form button[type=submit]').focus();
    });
  });
});
