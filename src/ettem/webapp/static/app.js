// ============================================================================
// Easy Table Tennis Event Manager - JavaScript
// ============================================================================

// Toast notification system
class ToastNotification {
    constructor() {
        this.container = this.createContainer();
    }

    createContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    show(message, type = 'info', duration = 5000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icon = this.getIcon(type);

        toast.innerHTML = `
            <div class="icon">${icon}</div>
            <div class="alert-content">
                <div class="alert-title">${this.getTitle(type)}</div>
                <div>${message}</div>
            </div>
        `;

        this.container.appendChild(toast);

        // Auto remove after duration
        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                this.container.removeChild(toast);
            }, 300);
        }, duration);
    }

    getIcon(type) {
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        return icons[type] || icons.info;
    }

    getTitle(type) {
        const titles = {
            success: 'Éxito',
            error: 'Error',
            warning: 'Advertencia',
            info: 'Información'
        };
        return titles[type] || titles.info;
    }

    success(message, duration) {
        this.show(message, 'success', duration);
    }

    error(message, duration) {
        this.show(message, 'error', duration);
    }

    warning(message, duration) {
        this.show(message, 'warning', duration);
    }

    info(message, duration) {
        this.show(message, 'info', duration);
    }
}

// Initialize toast system
const toast = new ToastNotification();

// Form validation and submission
function setupFormValidation() {
    const forms = document.querySelectorAll('form[data-validate]');

    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Custom validation logic can go here
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('is-invalid');
                } else {
                    field.classList.remove('is-invalid');
                }
            });

            if (!isValid) {
                e.preventDefault();
                toast.error('Por favor completa todos los campos requeridos');
            }
        });
    });
}

// Sidebar toggle for mobile
function setupSidebarToggle() {
    const sidebar = document.querySelector('.sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            if (sidebar.classList.contains('open')) {
                document.body.appendChild(overlay);
                overlay.addEventListener('click', () => {
                    sidebar.classList.remove('open');
                    document.body.removeChild(overlay);
                });
            }
        });
    }
}

// Confirm dialogs
function setupConfirmDialogs() {
    const confirmButtons = document.querySelectorAll('[data-confirm]');

    confirmButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

// Active nav link highlighting
function highlightActiveNavLink() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href && (currentPath === href || currentPath.startsWith(href + '/'))) {
            link.classList.add('active');
        }
    });
}

// Auto-dismiss alerts
function setupAutoDismissAlerts() {
    const alerts = document.querySelectorAll('.alert[data-auto-dismiss]');

    alerts.forEach(alert => {
        const duration = parseInt(alert.getAttribute('data-auto-dismiss')) || 5000;
        setTimeout(() => {
            alert.style.animation = 'fadeOut 0.3s ease';
            setTimeout(() => {
                alert.remove();
            }, 300);
        }, duration);
    });
}

// Match result validation
function setupMatchResultValidation() {
    const matchForms = document.querySelectorAll('form[data-match-form]');

    matchForms.forEach(form => {
        const walkoverCheckbox = form.querySelector('input[name="is_walkover"]');
        const setInputs = form.querySelectorAll('input[name^="set"]');
        const winnerSelect = form.querySelector('select[name="winner_id"]');

        if (walkoverCheckbox) {
            walkoverCheckbox.addEventListener('change', function() {
                const isWalkover = this.checked;

                setInputs.forEach(input => {
                    input.disabled = isWalkover;
                    if (isWalkover) {
                        input.value = '';
                    }
                });

                if (winnerSelect) {
                    winnerSelect.disabled = !isWalkover;
                }
            });
        }
    });
}

// Table sorting (simple client-side)
function setupTableSorting() {
    const sortableTables = document.querySelectorAll('table[data-sortable]');

    sortableTables.forEach(table => {
        const headers = table.querySelectorAll('th[data-sort]');

        headers.forEach(header => {
            header.style.cursor = 'pointer';
            header.addEventListener('click', function() {
                const column = this.getAttribute('data-sort');
                sortTable(table, column);
            });
        });
    });
}

function sortTable(table, column) {
    // Simple sorting implementation
    // Can be enhanced based on needs
    toast.info('Función de ordenamiento en desarrollo');
}

// Copy to clipboard
function setupCopyButtons() {
    const copyButtons = document.querySelectorAll('[data-copy]');

    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const text = this.getAttribute('data-copy');
            navigator.clipboard.writeText(text).then(() => {
                toast.success('Copiado al portapapeles');
            }).catch(() => {
                toast.error('Error al copiar');
            });
        });
    });
}

// Initialize all features on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    setupFormValidation();
    setupSidebarToggle();
    setupConfirmDialogs();
    highlightActiveNavLink();
    setupAutoDismissAlerts();
    setupMatchResultValidation();
    setupTableSorting();
    setupCopyButtons();

    // Show any flash messages from server
    const flashMessages = document.querySelectorAll('[data-flash-message]');
    console.log('Flash messages found:', flashMessages.length);
    flashMessages.forEach(msg => {
        const type = msg.getAttribute('data-flash-type') || 'info';
        const message = msg.getAttribute('data-flash-message');
        console.log('Showing flash message:', type, message);
        if (message && message.trim()) {
            toast[type](message);
        }
    });
});

// Utility functions
const utils = {
    formatDate(date) {
        return new Date(date).toLocaleDateString('es-ES');
    },

    formatTime(time) {
        return new Date(time).toLocaleTimeString('es-ES', {
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};

// Sidebar submenu toggle
function toggleSubmenu(event, category) {
    event.preventDefault();
    event.stopPropagation();

    const link = event.currentTarget;
    const submenu = document.getElementById('submenu-' + category);

    // Toggle expanded classes
    link.classList.toggle('expanded');
    submenu.classList.toggle('expanded');

    // If clicking on the link itself (not a submenu item), navigate
    if (event.target === link || event.target.closest('.nav-link-category') === link) {
        // Only navigate if we're collapsing (expanded class was just removed)
        if (!link.classList.contains('expanded')) {
            const href = link.getAttribute('data-href') || link.href;
            if (href) {
                window.location.href = href;
            }
        }
    }
}

// Auto-expand submenu for current page
document.addEventListener('DOMContentLoaded', function() {
    const currentPath = window.location.pathname;

    // Find all sublinks and check if any match current path
    document.querySelectorAll('.nav-sublink').forEach(sublink => {
        if (currentPath.includes(sublink.getAttribute('href'))) {
            // Find parent category and expand it
            const category = sublink.closest('.nav-category');
            if (category) {
                const categoryLink = category.querySelector('.nav-link-category');
                const submenu = category.querySelector('.nav-submenu');
                if (categoryLink && submenu) {
                    categoryLink.classList.add('expanded');
                    submenu.classList.add('expanded');
                }
            }
        }
    });
});

// Sidebar collapse/expand functionality
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');

    if (!sidebar) {
        console.error('[toggleSidebar] Sidebar element not found!');
        return;
    }

    sidebar.classList.toggle('collapsed');
    const isCollapsed = sidebar.classList.contains('collapsed');

    // Update toggle button icon
    const toggleIcon = document.querySelector('.toggle-icon');
    if (toggleIcon) {
        toggleIcon.textContent = isCollapsed ? '🏓' : '◀';
    }

    // Save state to localStorage
    localStorage.setItem('sidebarCollapsed', isCollapsed.toString());

    // If collapsing, close all submenus
    if (isCollapsed) {
        document.querySelectorAll('.nav-submenu.expanded').forEach(submenu => {
            submenu.classList.remove('expanded');
        });
        document.querySelectorAll('.nav-link-category.expanded').forEach(link => {
            link.classList.remove('expanded');
        });
    }
}

// Restore sidebar state on page load
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('sidebar');

    if (!sidebar) return;

    const storedState = localStorage.getItem('sidebarCollapsed');
    const toggleIcon = document.querySelector('.toggle-icon');

    // Only apply if we have a valid stored state
    if (storedState === 'true') {
        sidebar.classList.add('collapsed');
        if (toggleIcon) {
            toggleIcon.textContent = '🏓';
        }
    } else if (storedState === 'false') {
        sidebar.classList.remove('collapsed');
        if (toggleIcon) {
            toggleIcon.textContent = '◀';
        }
    }
    // If storedState is null (first time), leave it as default (expanded)

    // Make logo clickable when sidebar is collapsed
    const logo = document.querySelector('.logo');
    if (logo) {
        logo.addEventListener('click', function() {
            if (sidebar.classList.contains('collapsed')) {
                toggleSidebar();
            }
        });
    }
});

// Theme toggle functionality
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    if (newTheme === 'dark') {
        html.setAttribute('data-theme', 'dark');
    } else {
        html.removeAttribute('data-theme');
    }

    // Save preference
    localStorage.setItem('ettem_theme', newTheme);

    // Show notification
    const themeName = newTheme === 'dark' ? 'oscuro' : 'claro';
    toast.info(`Tema ${themeName} activado`);
}

// Export for use in other scripts
window.toast = toast;
window.utils = utils;
window.toggleSubmenu = toggleSubmenu;
window.toggleSidebar = toggleSidebar;
window.toggleTheme = toggleTheme;
