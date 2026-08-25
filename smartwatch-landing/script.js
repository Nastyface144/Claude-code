// Полоса прогресса скролла
const progressBar = document.getElementById('scroll-progress');
function updateProgress() {
  const scrollable = document.documentElement.scrollHeight - window.innerHeight;
  const ratio = scrollable > 0 ? (window.scrollY / scrollable) * 100 : 0;
  if (progressBar) progressBar.style.width = ratio + '%';
}
document.addEventListener('scroll', updateProgress, { passive: true });
updateProgress();

// Курсор-глоу в hero (только для устройств с точным указателем)
const cursorGlow = document.getElementById('cursor-glow');
const heroSection = document.querySelector('.hero');
if (cursorGlow && heroSection && window.matchMedia('(pointer: fine)').matches) {
  heroSection.addEventListener('mousemove', (e) => {
    cursorGlow.style.setProperty('--x', e.clientX + 'px');
    cursorGlow.style.setProperty('--y', e.clientY + 'px');
    cursorGlow.classList.add('is-active');
  });
  heroSection.addEventListener('mouseleave', () => {
    cursorGlow.classList.remove('is-active');
  });
}

// Мобильное меню
const burger = document.getElementById('burger');
const nav = document.getElementById('main-nav');

if (burger && nav) {
  burger.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('is-open');
    burger.setAttribute('aria-expanded', String(isOpen));
  });

  nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      nav.classList.remove('is-open');
      burger.setAttribute('aria-expanded', 'false');
    });
  });
}

// Плавное появление блоков при скролле
const revealEls = document.querySelectorAll('.reveal');

if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
  );

  revealEls.forEach((el) => observer.observe(el));
} else {
  revealEls.forEach((el) => el.classList.add('is-visible'));
}

// FAQ-аккордеон
document.querySelectorAll('.faq-question').forEach((btn) => {
  btn.addEventListener('click', () => {
    const item = btn.closest('.faq-item');
    const answer = item.querySelector('.faq-answer');
    const isOpen = btn.getAttribute('aria-expanded') === 'true';

    document.querySelectorAll('.faq-question').forEach((otherBtn) => {
      if (otherBtn !== btn) {
        otherBtn.setAttribute('aria-expanded', 'false');
        otherBtn.closest('.faq-item').querySelector('.faq-answer').style.maxHeight = null;
      }
    });

    btn.setAttribute('aria-expanded', String(!isOpen));
    answer.style.maxHeight = isOpen ? null : answer.scrollHeight + 'px';
  });
});
