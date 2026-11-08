const form = document.querySelector('#lead-form');
const status = document.querySelector('#form-status');
const menuButton = document.querySelector('.menu-toggle');
const mobileNav = document.querySelector('.mobile-nav');
const goal = (name) => { if (window.ym && window.ymId) window.ym(window.ymId, 'reachGoal', name); };
const cookieBanner = document.querySelector('#cookie-banner');
function startAnalytics() {
  if (!window.ymId || window.ym) return;
  window.ym = function () { (window.ym.a = window.ym.a || []).push(arguments); };
  window.ym.l = Date.now();
  const script = document.createElement('script');
  script.async = true;
  script.src = 'https://mc.yandex.ru/metrika/tag.js';
  document.head.append(script);
  window.ym(window.ymId, 'init', {clickmap: true, trackLinks: true, accurateTrackBounce: true});
}
if (cookieBanner) {
  const choice = localStorage.getItem('analytics-consent');
  if (choice === 'accept') startAnalytics();
  else if (!choice) cookieBanner.hidden = false;
  cookieBanner.querySelectorAll('[data-consent]').forEach(button => button.addEventListener('click', () => {
    const value = button.dataset.consent;
    localStorage.setItem('analytics-consent', value);
    cookieBanner.hidden = true;
    if (value === 'accept') startAnalytics();
  }));
}

menuButton?.addEventListener('click', () => {
  const opened = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!opened));
  menuButton.setAttribute('aria-label', opened ? 'Открыть меню' : 'Закрыть меню');
  mobileNav.hidden = opened;
});
mobileNav?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
  mobileNav.hidden = true;
  menuButton.setAttribute('aria-expanded', 'false');
}));

document.querySelectorAll('[data-goal]').forEach(link => link.addEventListener('click', () => goal(link.dataset.goal)));
document.querySelectorAll('[data-event]').forEach(link => link.addEventListener('click', () => {
  form.elements.event_type.value = link.dataset.event;
}));

const dateInput = form?.elements.event_date;
if (dateInput) {
  const today = new Date();
  dateInput.min = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
}
form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  status.textContent = 'Отправляем заявку…';
  status.className = 'form-status';
  const data = Object.fromEntries(new FormData(form));
  data.consent = form.elements.consent.checked;
  const query = new URLSearchParams(location.search);
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign']) data[key] = query.get(key) || '';
  try {
    const response = await fetch('/api/leads', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
    if (!response.ok) throw new Error(response.status === 429 ? 'Слишком много заявок. Попробуйте позже.' : 'Не удалось отправить заявку. Проверьте поля и повторите попытку.');
    status.textContent = 'Заявка сохранена. Спасибо!';
    status.className = 'form-status success';
    form.reset();
    goal('lead_sent');
  } catch (error) {
    status.textContent = error.message;
    status.className = 'form-status error';
  } finally { button.disabled = false; }
});

if ('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); }
  }), {threshold: .08});
  document.querySelectorAll('.reveal').forEach(element => observer.observe(element));
} else document.querySelectorAll('.reveal').forEach(element => element.classList.add('visible'));

const dialog = document.querySelector('#video-dialog');
document.querySelector('.play-video')?.addEventListener('click', event => {
  const source = event.currentTarget.dataset.video;
  const url = new URL(source, location.href);
  if (!['https:', 'http:'].includes(url.protocol)) return;
  const iframe = document.createElement('iframe');
  iframe.src = url.href;
  iframe.title = 'Видеовизитка Егора';
  iframe.allow = 'autoplay; fullscreen; picture-in-picture';
  iframe.allowFullscreen = true;
  document.querySelector('#video-container').replaceChildren(iframe);
  dialog.showModal();
});
document.querySelector('.close-video')?.addEventListener('click', () => dialog.close());
dialog?.addEventListener('close', () => document.querySelector('#video-container').replaceChildren());
