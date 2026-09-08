const menuButton = document.querySelector('#menuButton');
const sidebar = document.querySelector('#sidebar');

if (menuButton && sidebar) {
  menuButton.addEventListener('click', () => sidebar.classList.toggle('open'));
}
