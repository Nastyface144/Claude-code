// Sticky header on scroll
const header = document.querySelector('.site-header');
const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 40);
onScroll();
window.addEventListener('scroll', onScroll, { passive: true });

// Mobile menu
const burger = document.getElementById('burger');
const nav = document.getElementById('main-nav');
burger.addEventListener('click', () => {
  const isOpen = nav.classList.toggle('open');
  burger.classList.toggle('open', isOpen);
  burger.setAttribute('aria-expanded', String(isOpen));
});
nav.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    nav.classList.remove('open');
    burger.classList.remove('open');
    burger.setAttribute('aria-expanded', 'false');
  });
});

// Scroll reveal animations
const revealTargets = document.querySelectorAll(
  '.problem-card, .feature-card, .guarantee-card, .process-steps li, .section-eyebrow, h2, .hero-lead'
);
revealTargets.forEach((el) => el.classList.add('reveal'));

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.15 }
);
revealTargets.forEach((el) => observer.observe(el));

// FAQ accordion
document.querySelectorAll('.faq-question').forEach((btn) => {
  btn.addEventListener('click', () => {
    const answer = btn.nextElementSibling;
    const isOpen = btn.getAttribute('aria-expanded') === 'true';

    document.querySelectorAll('.faq-question').forEach((other) => {
      other.setAttribute('aria-expanded', 'false');
      other.nextElementSibling.style.maxHeight = null;
    });

    if (!isOpen) {
      btn.setAttribute('aria-expanded', 'true');
      answer.style.maxHeight = answer.scrollHeight + 'px';
    }
  });
});

// Hero cursor spotlight + parallax facade
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const hero = document.querySelector('.hero');
const spotlight = document.getElementById('spotlight');
if (hero && spotlight && !prefersReducedMotion) {
  hero.addEventListener('pointermove', (e) => {
    const rect = hero.getBoundingClientRect();
    spotlight.style.setProperty('--mx', `${e.clientX - rect.left}px`);
    spotlight.style.setProperty('--my', `${e.clientY - rect.top}px`);
    hero.style.setProperty('--mx', `${e.clientX - rect.left}px`);
    hero.style.setProperty('--my', `${e.clientY - rect.top}px`);
  });
}

const facade = document.getElementById('facade');
if (facade && !prefersReducedMotion) {
  window.addEventListener(
    'scroll',
    () => {
      if (window.scrollY < window.innerHeight) {
        facade.style.setProperty('--parallax', `${window.scrollY * -0.12}px`);
      }
    },
    { passive: true }
  );
}

// Count-up numbers in hero stats
document.querySelectorAll('.stat-num').forEach((el) => {
  const target = parseFloat(el.dataset.target);
  const decimals = parseInt(el.dataset.decimals || '0', 10);
  const suffix = el.dataset.suffix || '';

  if (prefersReducedMotion) {
    el.innerHTML = target.toFixed(decimals) + suffix;
    return;
  }

  const duration = 1400;
  const start = performance.now() + 300;

  const tick = (now) => {
    const elapsed = now - start;
    if (elapsed < 0) {
      requestAnimationFrame(tick);
      return;
    }
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.innerHTML = (target * eased).toFixed(decimals) + suffix;
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});

// Contact form (client-side only — no backend wired up yet)
const form = document.getElementById('contact-form');
const fields = document.getElementById('form-fields');
const success = document.getElementById('form-success');

form.addEventListener('submit', (e) => {
  e.preventDefault();
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  fields.hidden = true;
  success.hidden = false;
});
