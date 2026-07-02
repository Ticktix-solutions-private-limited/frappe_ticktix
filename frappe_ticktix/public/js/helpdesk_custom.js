// Remove Support and Docs menu items from Helpdesk sidebar
// This runs after the Helpdesk Vue app is mounted

(function() {
    'use strict';
    
    // Only run on Helpdesk pages
    if (!window.location.pathname.startsWith('/helpdesk')) {
        return;
    }
    
    console.log('[TickTix] Helpdesk customization loaded');
    
    // Function to hide menu items containing specific text
    function hideHelpdeskMenuItems() {
        // Target all buttons and links that might be menu items
        const allElements = document.querySelectorAll('button, a, div[role="menuitem"]');
        
        let hiddenCount = 0;
        allElements.forEach(function(element) {
            const text = element.textContent.trim();
            
            // Hide Support and Docs menu items
            if (text === 'Support' || text === 'Docs') {
                let targetElement = element;
                
                // Try to find the parent menu item container
                // Go up the DOM tree to find a suitable container
                for (let i = 0; i < 5; i++) {
                    if (targetElement.parentElement) {
                        const parent = targetElement.parentElement;
                        // Check if parent looks like a menu item container
                        if (parent.tagName === 'DIV' && parent.children.length <= 3) {
                            targetElement = parent;
                        } else {
                            break;
                        }
                    }
                }
                
                targetElement.style.display = 'none';
                targetElement.style.visibility = 'hidden';
                targetElement.style.height = '0';
                targetElement.style.overflow = 'hidden';
                targetElement.classList.add('hide-helpdesk-support-docs');
                hiddenCount++;
            }
        });
        
        if (hiddenCount > 0) {
            console.log(`[TickTix] Hidden ${hiddenCount} Helpdesk menu items`);
        }
    }
    
    // Create a mutation observer to watch for dropdown menus being added
    const observer = new MutationObserver(function(mutations) {
        hideHelpdeskMenuItems();
    });
    
    // Start observing when ready
    function startObserving() {
        if (document.body) {
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
            
            // Run immediately
            hideHelpdeskMenuItems();
            
            // Also run after delays to catch late-rendered elements
            setTimeout(hideHelpdeskMenuItems, 500);
            setTimeout(hideHelpdeskMenuItems, 1000);
            setTimeout(hideHelpdeskMenuItems, 2000);
        }
    }
    
    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startObserving);
    } else {
        startObserving();
    }
    
    // Also listen for route changes in Vue apps
    window.addEventListener('popstate', function() {
        setTimeout(hideHelpdeskMenuItems, 300);
    });
})();
