// TickTix Split-Screen Login Enhancement

$(document).ready(function() {
    // Add body class for styling
    $('body').addClass('login-page');
    
    // Move page-card-head inside login-content.page-card at the top
    // Wait for complete page render before DOM manipulation
    setTimeout(function() {
        const $pageCardHead = $('.for-login .page-card-head');
        const $loginContent = $('.for-login .login-content.page-card');
        
        if ($pageCardHead.length && $loginContent.length) {
            // Remove from current position and add to top of login-content
            $pageCardHead.prependTo($loginContent);
            console.log('Header moved inside login card');
        } else {
            console.log('Elements not found - Header:', $pageCardHead.length, 'Login content:', $loginContent.length);
        }
    }, 100); // Small delay to ensure complete rendering
    
    // Update button text for TickTix login
    $('.btn-login-option').each(function() {
        const $btn = $(this);
        if ($btn.hasClass('btn-ticktix') || $btn.text().toLowerCase().includes('ticktix')) {
            $btn.text('Login with TickTix');
        }
    });
    
    // Basic accessibility
    $('.btn-login-option').attr('aria-label', function() {
        return $(this).text() + ' Identity Provider';
    });
});
