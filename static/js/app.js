const menuButton = document.querySelector('#menuButton');
const sidebar = document.querySelector('#sidebar');
const menuBackdrop = document.querySelector('#menuBackdrop');
const mobileMenu = window.matchMedia('(max-width: 900px)');

if (menuButton && sidebar && menuBackdrop) {
  const setMenu = (open, restoreFocus = false) => {
    sidebar.classList.toggle('open', open);
    sidebar.inert = mobileMenu.matches && !open;
    menuBackdrop.hidden = !open;
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    document.body.classList.toggle('menu-open', open);
    if (open) sidebar.querySelector('a').focus();
    else if (restoreFocus) menuButton.focus();
  };
  menuButton.addEventListener('click', () => setMenu(!sidebar.classList.contains('open')));
  menuBackdrop.addEventListener('click', () => setMenu(false, true));
  document.addEventListener('keydown', (event) => {
    if (!sidebar.classList.contains('open')) return;
    if (event.key === 'Escape') setMenu(false, true);
    if (event.key === 'Tab') {
      const links = [...sidebar.querySelectorAll('a')];
      if (event.shiftKey && document.activeElement === links[0]) {
        event.preventDefault(); links.at(-1).focus();
      } else if (!event.shiftKey && document.activeElement === links.at(-1)) {
        event.preventDefault(); links[0].focus();
      }
    }
  });
  sidebar.addEventListener('click', (event) => {
    if (event.target.closest('a')) setMenu(false);
  });
  mobileMenu.addEventListener('change', () => setMenu(false));
  setMenu(false);
}

const conferenceForm = document.querySelector('#conferenceForm');
if (conferenceForm) {
  const items = [...conferenceForm.querySelectorAll('.conference-item')];
  const summaries = [...conferenceForm.querySelectorAll('.item-summary')];
  const currentInput = document.querySelector('#currentItem');
  const position = document.querySelector('#itemPosition');
  const allItems = document.querySelector('#allItems');
  const allButton = document.querySelector('#allItemsButton');
  const previous = document.querySelector('#previousItem');
  const next = document.querySelector('#nextItem');
  const saveNext = document.querySelector('#saveNext');
  const mobile = window.matchMedia('(max-width: 600px)');
  let current = Math.max(0, Math.min(Math.trunc(Number(currentInput.value)) || 0, items.length - 1));
  let showingAll = false;
  let dirty = false;
  let submitting = false;
  conferenceForm.classList.add('sequential-ready');

  function showItem(index, focus = true) {
    current = index;
    currentInput.value = current;
    showingAll = false;
    render();
    if (focus && mobile.matches) {
      position.focus({ preventScroll: true });
      position.scrollIntoView({ block: 'start', behavior: 'auto' });
    }
  }
  function render() {
    items.forEach((item, index) => { item.hidden = mobile.matches && (showingAll || index !== current); });
    allItems.hidden = !mobile.matches || !showingAll;
    allButton.textContent = showingAll ? 'Voltar ao item' : 'Ver todos os itens';
    allButton.setAttribute('aria-expanded', String(showingAll));
    position.textContent = items.length ? `Item ${current + 1} de ${items.length}` : 'Nenhum item';
    previous.disabled = current === 0;
    if (next) next.disabled = current >= items.length - 1;
    if (saveNext) {
      saveNext.disabled = !items.length;
      saveNext.textContent = current === items.length - 1 ? 'Salvar último item' : 'Salvar e próximo';
    }
    conferenceForm.classList.toggle('showing-all', showingAll);
  }
  previous.addEventListener('click', () => showItem(Math.max(0, current - 1)));
  if (next) next.addEventListener('click', () => showItem(Math.min(items.length - 1, current + 1)));
  allButton.addEventListener('click', () => { showingAll = !showingAll; render(); });
  summaries.forEach((summary, index) => summary.addEventListener('click', () => showItem(index)));
  conferenceForm.addEventListener('input', (event) => {
    dirty = true;
    const item = event.target.closest('.conference-item');
    if (!item) return;
    const summary = summaries[Number(item.dataset.itemIndex)];
    summary.querySelector('[data-summary-quantity]').textContent = item.querySelector('[inputmode="decimal"]').value || '—';
    summary.querySelector('[data-draft]').hidden = false;
  });
  // Reveal invalid fields before native validation attempts to focus them.
  conferenceForm.addEventListener('invalid', (event) => {
    const item = event.target.closest('.conference-item');
    if (item) showItem(Number(item.dataset.itemIndex), false);
  }, true);
  conferenceForm.addEventListener('submit', (event) => {
    if (submitting) { event.preventDefault(); return; }
    submitting = true;
  });
  window.addEventListener('beforeunload', (event) => {
    if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
  });
  window.addEventListener('pageshow', () => { submitting = false; });
  mobile.addEventListener('change', render);
  showItem(current, false);
}
