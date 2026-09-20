(() => {
    const track = document.getElementById('reviews-container');
    if (!track) return;
    const carousel = document.getElementById('reviews-carousel');
    const message = document.getElementById('reviews-message');
    const previous = document.getElementById('reviews-prev');
    const next = document.getElementById('reviews-next');
    const position = document.getElementById('reviews-position');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function safeUrl(value) {
        try {
            const url = new URL(value);
            return url.protocol === 'https:' ? url.href : null;
        } catch { return null; }
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        node.className = className;
        if (text) node.textContent = text;
        return node;
    }

    function externalLink(className, text, url) {
        const node = element('a', className, text);
        node.href = url;
        node.target = '_blank';
        node.rel = 'noopener noreferrer';
        return node;
    }

    function renderReview(review, index, count, mapsUrl) {
        const card = element('article', 'review-card');
        card.setAttribute('aria-roledescription', 'slide');
        card.setAttribute('aria-label', `Review ${index + 1} of ${count}`);
        const author = element('div', 'review-author');
        const photo = safeUrl(review.profile_photo_url);
        if (photo) {
            const avatar = element('img', 'review-avatar');
            avatar.src = photo;
            avatar.alt = '';
            avatar.loading = 'lazy';
            avatar.addEventListener('error', () => avatar.remove(), { once: true });
            author.append(avatar);
        }
        const identity = element('div', 'review-identity');
        const profile = safeUrl(review.author_url);
        const name = review.author_name || 'Google user';
        identity.append(profile ? externalLink('review-author-name', name, profile) : element('span', 'review-author-name', name));
        identity.append(element('span', 'review-date', review.relative_time));
        author.append(identity);
        card.append(author);
        if (Number.isFinite(review.rating) && review.rating >= 0 && review.rating <= 5) {
            const stars = element('div', 'review-stars', '★'.repeat(Math.round(review.rating)) + '☆'.repeat(5 - Math.round(review.rating)));
            stars.setAttribute('role', 'img');
            stars.setAttribute('aria-label', `${review.rating} out of 5 stars`);
            card.append(stars);
        }
        card.append(element('p', 'review-text', review.text || 'This customer left a rating without a written review.'));
        card.append(externalLink('review-source', 'View on Google Maps →', safeUrl(review.google_maps_url) || mapsUrl));
        return card;
    }

    function updateControls() {
        const cards = [...track.children];
        const left = track.getBoundingClientRect().left;
        const visible = cards.filter(card => {
            const bounds = card.getBoundingClientRect();
            return bounds.right > left + 10 && bounds.left < left + track.clientWidth - 10;
        });
        if (!visible.length) return;
        const first = cards.indexOf(visible[0]) + 1;
        const last = cards.indexOf(visible[visible.length - 1]) + 1;
        position.textContent = `${first === last ? first : `${first}–${last}`} of ${cards.length}`;
        previous.disabled = track.scrollLeft <= 2;
        next.disabled = track.scrollLeft >= track.scrollWidth - track.clientWidth - 2;
        document.getElementById('reviews-controls').hidden = track.scrollWidth <= track.clientWidth + 2;
    }

    function move(direction) {
        const card = track.firstElementChild;
        if (!card) return;
        const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
        track.scrollBy({ left: direction * (card.getBoundingClientRect().width + gap), behavior: reducedMotion.matches ? 'instant' : 'smooth' });
    }
    previous.addEventListener('click', () => move(-1));
    next.addEventListener('click', () => move(1));
    track.addEventListener('keydown', event => {
        if (event.target !== track) return;
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            move(event.key === 'ArrowLeft' ? -1 : 1);
        }
    });
    let scrollTimer;
    track.addEventListener('scroll', () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(updateControls, 120);
    }, { passive: true });
    new ResizeObserver(updateControls).observe(track);

    async function load() {
        message.textContent = 'Loading customer reviews…';
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch('/api/reviews', { signal: controller.signal, cache: 'no-store' });
            if (!response.ok) throw new Error('Reviews unavailable');
            const data = await response.json();
            const mapsUrl = safeUrl(data.google_maps_url) || document.querySelector('.reviews-google-link').href;
            if (Number.isFinite(data.rating) && Number.isInteger(data.total_reviews)) {
                document.getElementById('reviews-summary').textContent = `${data.rating.toFixed(1)} out of 5 · ${data.total_reviews} Google reviews`;
            }
            if (!Array.isArray(data.reviews) || !data.reviews.length) {
                message.textContent = 'Visit Google Maps to see the latest customer reviews.';
                return;
            }
            data.reviews.forEach((review, index) => track.append(renderReview(review, index, data.reviews.length, mapsUrl)));
            message.hidden = true;
            carousel.hidden = false;
            updateControls();
        } catch {
            message.textContent = 'Reviews couldn’t load right now. You can still read them on Google using the link above.';
        } finally {
            clearTimeout(timeout);
        }
    }
    // Load only when the visitor approaches the reviews section.
    const observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) {
            observer.disconnect();
            load();
        }
    }, { rootMargin: '300px' });
    observer.observe(carousel.parentElement);
})();
