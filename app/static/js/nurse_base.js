/**
 * static/js/nurse_base.js
 */
document.addEventListener('DOMContentLoaded', () => {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    const backToTopBtn = document.getElementById('backToTop');

    window.addEventListener('scroll', () => {
        if (window.scrollY > 300) {
            backToTopBtn.classList.add('show');
        } else {
            backToTopBtn.classList.remove('show');
        }
    });

    if (backToTopBtn) {
        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.add('active');
            overlay.classList.add('active');
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        });
    }

    const userMenuToggle  = document.getElementById('userMenuToggle');
    const userDropdown    = document.getElementById('userDropdown');
    const userMenuCaret   = document.getElementById('userMenuCaret');
    const avatarFileInput = document.getElementById('avatarFileInput');
    const avatarUploadForm = document.getElementById('avatarUploadForm');

    function openUserMenu() {
        userDropdown.classList.add('open');
        userMenuCaret.textContent = '▼';
    }
    function closeUserMenu() {
        userDropdown.classList.remove('open');
        userMenuCaret.textContent = '▲';
    }

    if (userMenuToggle) {
        userMenuToggle.addEventListener('click', () => {
            userDropdown.classList.contains('open') ? closeUserMenu() : openUserMenu();
        });
        userMenuToggle.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); userMenuToggle.click(); }
        });
    }

    document.addEventListener('click', e => {
        if (userDropdown && userMenuToggle && !userMenuToggle.contains(e.target) && !userDropdown.contains(e.target)) {
            closeUserMenu();
        }
    });

    if (avatarFileInput) {
        avatarFileInput.addEventListener('change', () => {
            if (avatarFileInput.files.length) avatarUploadForm.submit();
        });
    }

    let touchStartX = 0;
    let touchEndX = 0;

    // Record where the finger first touches the screen
    document.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    // Record where the finger leaves the screen and calculate
    document.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });

    function handleSwipe() {
        if (sidebar.classList.contains('active')) {
            if (touchStartX - touchEndX > 50) {
                // Close the sidebar!
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
            }
        }
    }
});
