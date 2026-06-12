document.querySelectorAll('.flake-img').forEach(image => {
    image.addEventListener('click', () => {
        const modal = document.getElementById('flakeModal');
        const modalImage = document.getElementById('flakeModalImg');

        if (!modal || !modalImage) {
            return;
        }

        modal.style.display = 'block';
        modalImage.src = image.src;
    });
});

const flakeClose = document.querySelector('.flake-close');
if (flakeClose) {
    flakeClose.addEventListener('click', () => {
        const modal = document.getElementById('flakeModal');
        if (modal) {
            modal.style.display = 'none';
        }
    });
}

async function loadReviews() {
    const container = document.getElementById('reviews-container');
    if (!container) {
        return;
    }

    try {
        const response = await fetch('/api/reviews');
        const data = await response.json();

        container.innerHTML = '';

        if (!data.reviews || data.reviews.length === 0) {
            container.innerHTML = `
                <div class="swiper-slide review-card">
                    <p class="review-text">Reviews are currently unavailable.</p>
                </div>
            `;
        } else {
            data.reviews
                .sort((a, b) => b.rating - a.rating)
                .slice(0, 5)
                .forEach(review => {
                    const text = review.text && review.text.length > 200
                        ? `${review.text.substring(0, 200)}...`
                        : review.text || 'No review text available.';

                    const slide = document.createElement('div');
                    slide.className = 'swiper-slide review-card animate-on-scroll';

                    const avatar = document.createElement('img');
                    avatar.className = 'review-avatar';
                    avatar.alt = '';
                    avatar.loading = 'lazy';
                    avatar.src = review.profile_photo_url || '';
                    avatar.onerror = () => {
                        avatar.style.display = 'none';
                    };

                    const reviewText = document.createElement('p');
                    reviewText.className = 'review-text';
                    reviewText.textContent = `"${text}"`;

                    const reviewerName = document.createElement('p');
                    reviewerName.className = 'reviewer-name';
                    reviewerName.textContent = `- ${review.author_name || 'Google User'}`;

                    slide.append(avatar, reviewText, reviewerName);
                    container.appendChild(slide);
                });
        }

        if (window.reviewSwiper) {
            window.reviewSwiper.destroy(true, true);
        }

        window.reviewSwiper = new Swiper('.reviews-swiper', {
            slidesPerView: 1,
            centeredSlides: true,
            autoHeight: true,
            spaceBetween: 20,
            loop: false,
            navigation: {
                nextEl: '.swiper-button-next',
                prevEl: '.swiper-button-prev',
            },
        });
    } catch (error) {
        console.error('Error loading reviews:', error);

        container.innerHTML = `
            <div class="swiper-slide review-card">
                <p class="review-text">Reviews are currently unavailable.</p>
            </div>
        `;

        if (window.reviewSwiper) {
            window.reviewSwiper.destroy(true, true);
        }

        window.reviewSwiper = new Swiper('.reviews-swiper', {
            slidesPerView: 1,
            spaceBetween: 20,
            loop: true,
            navigation: {
                nextEl: '.swiper-button-next',
                prevEl: '.swiper-button-prev',
            },
            breakpoints: {
                768: { slidesPerView: 2 },
            },
        });
    }
}

document.addEventListener('DOMContentLoaded', loadReviews);
