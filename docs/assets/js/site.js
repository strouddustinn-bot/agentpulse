(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const reveals = document.querySelectorAll('.reveal');

  if (reduceMotion || !('IntersectionObserver' in window)) {
    reveals.forEach((el) => el.classList.add('is-visible'));
  } else {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -60px' },
    );
    reveals.forEach((el) => observer.observe(el));
  }

  const header = document.querySelector('.site-header');
  const syncHeader = () => header?.classList.toggle('is-scrolled', window.scrollY > 24);
  syncHeader();
  window.addEventListener('scroll', syncHeader, { passive: true });

  const visual = document.querySelector('.hero-visual');
  if (visual && !reduceMotion && window.matchMedia('(pointer: fine)').matches) {
    visual.addEventListener('pointermove', (event) => {
      const rect = visual.getBoundingClientRect();
      visual.style.setProperty('--mx', `${event.clientX - rect.left}px`);
      visual.style.setProperty('--my', `${event.clientY - rect.top}px`);
    });
  }
})();
