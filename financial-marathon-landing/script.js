// Mobile navigation toggle
const burger = document.getElementById('burger');
const mainNav = document.getElementById('main-nav');

if (burger && mainNav) {
  burger.addEventListener('click', () => {
    const isOpen = mainNav.classList.toggle('is-open');
    burger.setAttribute('aria-expanded', String(isOpen));
  });

  mainNav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      mainNav.classList.remove('is-open');
      burger.setAttribute('aria-expanded', 'false');
    });
  });
}

// Scroll reveal animation
const revealItems = document.querySelectorAll('.reveal');
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

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

  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add('is-visible'));
}

// Animated counters (percentages in the hero card, stats in the trust badges)
function animateCount(el, target, duration = 1300) {
  if (prefersReducedMotion) {
    el.textContent = target;
    return;
  }
  const start = performance.now();
  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(target * eased);
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function animateProgressBar(el, duration = 1300) {
  const target = Number(el.dataset.target || 0);
  const fill = el.querySelector('span');
  if (!fill) return;
  if (prefersReducedMotion) {
    fill.style.width = target + '%';
    return;
  }
  const start = performance.now();
  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    fill.style.width = target * eased + '%';
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

const countTargets = document.querySelectorAll('.count-up');
const progressBar = document.getElementById('visual-progress-bar');

if ('IntersectionObserver' in window) {
  const countObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        if (entry.target.classList.contains('count-up')) {
          animateCount(entry.target, Number(entry.target.dataset.target || 0));
        } else if (entry.target === progressBar) {
          animateProgressBar(entry.target);
        }
        countObserver.unobserve(entry.target);
      });
    },
    { threshold: 0.4 }
  );

  countTargets.forEach((el) => countObserver.observe(el));
  if (progressBar) countObserver.observe(progressBar);
} else {
  countTargets.forEach((el) => animateCount(el, Number(el.dataset.target || 0)));
  if (progressBar) animateProgressBar(progressBar);
}

// Spotlight hover glow that follows the cursor on cards
if (!prefersReducedMotion && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
  document.querySelectorAll('.spotlight').forEach((card) => {
    card.addEventListener('mousemove', (event) => {
      const rect = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${event.clientX - rect.left}px`);
      card.style.setProperty('--my', `${event.clientY - rect.top}px`);
    });
  });

  // Subtle parallax on the hero background blobs
  const heroSection = document.getElementById('hero-parallax');
  if (heroSection) {
    const blobs = heroSection.querySelectorAll('.hero-blob');
    heroSection.addEventListener('mousemove', (event) => {
      const rect = heroSection.getBoundingClientRect();
      const relX = (event.clientX - rect.left) / rect.width - 0.5;
      const relY = (event.clientY - rect.top) / rect.height - 0.5;
      blobs.forEach((blob) => {
        const depth = Number(blob.dataset.depth || 1) * 14;
        blob.style.transform = `translate(${relX * depth}px, ${relY * depth}px)`;
      });
    });
    heroSection.addEventListener('mouseleave', () => {
      blobs.forEach((blob) => { blob.style.transform = ''; });
    });
  }
}

// Signup form handling.
// NOTE: there is no backend wired up yet — this only validates the fields
// and swaps in a success state. Replace the block inside the submit
// handler with a real request to your CRM / email service before launch.
const form = document.getElementById('signup-form');
const successState = document.getElementById('signup-success');

if (form && successState) {
  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const nameInput = document.getElementById('name');
    const emailInput = document.getElementById('email');
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    let isValid = true;

    if (!nameInput.value.trim()) {
      nameInput.classList.add('is-invalid');
      isValid = false;
    } else {
      nameInput.classList.remove('is-invalid');
    }

    if (!emailPattern.test(emailInput.value.trim())) {
      emailInput.classList.add('is-invalid');
      isValid = false;
    } else {
      emailInput.classList.remove('is-invalid');
    }

    if (!isValid) return;

    // TODO: send { name, email } to your actual signup endpoint here.
    form.hidden = true;
    successState.hidden = false;
  });
}
