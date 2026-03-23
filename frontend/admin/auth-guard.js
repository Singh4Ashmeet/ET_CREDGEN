// Auth Guard — redirect to login if no valid token
(function() {
    const token = sessionStorage.getItem('admin_token');
    if (!token) {
        window.location.href = '/admin/login';
        return;
    }

    // Verify token is still valid
    fetch('/auth/me', {
        headers: { 'Authorization': 'Bearer ' + token }
    }).then(r => {
        if (!r.ok) {
            sessionStorage.removeItem('admin_token');
            sessionStorage.removeItem('admin_refresh');
            window.location.href = '/admin/login';
        }
    }).catch(() => {
        window.location.href = '/admin/login';
    });
})();

function getToken() {
    return sessionStorage.getItem('admin_token');
}

function authHeaders() {
    return {
        'Authorization': 'Bearer ' + getToken(),
        'Content-Type': 'application/json',
    };
}

function logout() {
    fetch('/auth/logout', {
        method: 'POST',
        headers: authHeaders()
    }).finally(() => {
        sessionStorage.clear();
        window.location.href = '/admin/login';
    });
}
