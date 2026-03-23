(function() {
    // Default Config
    const config = Object.assign({
        primaryColor: '#4f46e5',
        bankName: 'Bank',
        logoUrl: '',
        welcomeMessage: 'Hi! I can help you with a loan.',
        position: 'bottom-right',
        showBranding: true
    }, window.CredGenConfig || {});

    // Styles
    const style = document.createElement('style');
    style.innerHTML = `
        .cg-widget-fab {
            position: fixed; ${config.position.includes('left') ? 'left: 20px;' : 'right: 20px;'} bottom: 20px;
            width: 60px; height: 60px; border-radius: 50%;
            background: ${config.primaryColor}; color: white;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border: none; cursor: pointer; z-index: 99999;
            display: flex; align-items: center; justify-content: center;
            font-size: 24px; transition: transform 0.2s;
        }
        .cg-widget-fab:hover { transform: scale(1.05); }
        
        .cg-widget-container {
            position: fixed; ${config.position.includes('left') ? 'left: 20px;' : 'right: 20px;'} bottom: 90px;
            width: 380px; height: 600px; max-height: 80vh;
            background: white; border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            z-index: 99999; display: none; flex-direction: column;
            overflow: hidden; border: 1px solid #e5e7eb;
            font-family: 'Inter', sans-serif;
        }
        
        .cg-widget-header {
            background: ${config.primaryColor}; color: white;
            padding: 16px; display: flex; justify-content: space-between; align-items: center;
        }
        
        .cg-iframe { width: 100%; height: 100%; border: none; }
        
        .cg-close-btn { background: none; border: none; color: white; font-size: 24px; cursor: pointer; }
        
        @media (max-width: 480px) {
            .cg-widget-container {
                inset: 0; width: 100%; height: 100%; max-height: none;
                bottom: 0; right: 0; left: 0; border-radius: 0;
            }
        }
    `;
    document.head.appendChild(style);

    // Elements
    const fab = document.createElement('button');
    fab.className = 'cg-widget-fab';
    fab.innerHTML = '💬';
    fab.setAttribute('aria-label', 'Open Chat');
    
    const container = document.createElement('div');
    container.className = 'cg-widget-container';
    
    // Header
    const header = document.createElement('div');
    header.className = 'cg-widget-header';
    header.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;">
            ${config.logoUrl ? `<img src="${config.logoUrl}" style="width:24px;height:24px;">` : ''}
            <strong>${config.bankName}</strong>
        </div>
    `;
    const closeBtn = document.createElement('button');
    closeBtn.className = 'cg-close-btn';
    closeBtn.innerHTML = '×';
    closeBtn.onclick = toggleWidget;
    header.appendChild(closeBtn);
    container.appendChild(header);

    // Iframe (loading the main chat app)
    // Assuming the main app is served at / or /chat-widget
    // Since we are rewriting index.html, we can use /frontend/index.html if served correctly, 
    // or just assume root / is the chat app.
    // For this refactor, let's assume root / is the app.
    const iframe = document.createElement('iframe');
    iframe.className = 'cg-iframe';
    iframe.src = '/'; 
    container.appendChild(iframe);

    // Footer Branding
    if (config.showBranding) {
        const footer = document.createElement('div');
        footer.style.cssText = 'padding: 8px; text-align: center; font-size: 10px; color: #6b7280; background: #f9fafb; border-top: 1px solid #e5e7eb;';
        footer.innerHTML = 'Powered by <strong>CredGen AI</strong>';
        container.appendChild(footer);
    }

    document.body.appendChild(fab);
    document.body.appendChild(container);

    // Toggle Logic
    let isOpen = false;
    function toggleWidget() {
        isOpen = !isOpen;
        container.style.display = isOpen ? 'flex' : 'none';
        fab.style.display = isOpen ? 'none' : 'flex';
        
        if (isOpen && window.innerWidth < 480) {
            document.body.style.overflow = 'hidden'; // Prevent background scroll
        } else {
            document.body.style.overflow = '';
        }
    }

    fab.addEventListener('click', toggleWidget);

    // Visual Viewport Fix for Mobile Keyboard
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            if (isOpen && window.innerWidth < 480) {
                container.style.height = `${window.visualViewport.height}px`;
                // Adjust iframe height if needed
            }
        });
    }

})();
