/* Artifact ID: b8d940ed-82df-43f5-abc1-ddefd356b867 */
/* Version: a8b9c0d1-e2f3-g4h5-i6j7-k8l9m0n1o2 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('main.js loaded successfully');

    // Global state
    let currentQuery = '';
    let currentMinRelevance = 10;
    let currentPage = 1;
    let totalPages = 1;
    const resultsPerPage = 25;
    let filterCounts = { remove: {}, add: {} };
    let currentEmails = [];
    let currentConversationEmails = [];
    let currentThemes = [];
    let currentConversationThemes = [];
    let deepAnalysisSessionId = null;
    let deepAnalysisEmails = [];
    let deepConversationAnalysisSessionId = null;
    let deepConversationAnalysisEmails = [];

    // Modal elements
    const modal = document.getElementById('email-modal');
    const closeModal = document.querySelector('.close');
    const modalContent = document.getElementById('email-details');

    // Initialize modal if not present
    if (!modal || !closeModal || !modalContent) {
        console.warn('Email modal elements not found, creating dynamically');
        const newModal = document.createElement('div');
        newModal.id = 'email-modal';
        newModal.className = 'modal';
        newModal.style.display = 'none';
        newModal.innerHTML = `
            <div class="modal-content">
                <span class="close">×</span>
                <div id="email-details"></div>
                <button id="not-relevant">Marcar como No Relevante</button>
            </div>
        `;
        document.body.appendChild(newModal);
    }

    // Wait for all scripts to load
    window.onload = () => {
        // Initialize modules
        if (typeof SearchModule !== 'undefined') {
            SearchModule.init({
                currentQuery,
                currentMinRelevance,
                currentPage,
                resultsPerPage,
                filterCounts,
                currentEmails,
                setCurrentEmails: (emails) => { 
                    console.log('Setting currentEmails:', emails);
                    currentEmails = emails; 
                },
                setFilterCounts: (counts) => { 
                    console.log('Setting filterCounts:', counts);
                    filterCounts = counts; 
                },
                setTotalPages: (pages) => { 
                    console.log('Setting totalPages:', pages);
                    totalPages = pages; 
                }
            });
            console.log('SearchModule initialized');
        }

        if (typeof ThemesModule !== 'undefined') {
            ThemesModule.init({
                currentThemes,
                setCurrentThemes: (themes) => {
                    console.log('Setting currentThemes:', themes);
                    currentThemes = themes || [];
                    ThemesModule.currentThemes = currentThemes;
                    console.log('Synchronized currentThemes with ThemesModule:', ThemesModule.currentThemes);
                }
            });
            console.log('ThemesModule initialized');
        }

        if (typeof DeepAnalysisModule !== 'undefined') {
            DeepAnalysisModule.init({
                deepAnalysisSessionId,
                deepAnalysisEmails,
                setDeepAnalysisSessionId: (id) => { 
                    console.log('Setting deepAnalysisSessionId:', id);
                    deepAnalysisSessionId = id;
                    DeepAnalysisModule.deepAnalysisSessionId = id;
                    console.log('Synchronized deepAnalysisSessionId with DeepAnalysisModule:', DeepAnalysisModule.deepAnalysisSessionId);
                },
                setDeepAnalysisEmails: (emails) => { 
                    console.log('Setting deepAnalysisEmails:', emails);
                    deepAnalysisEmails = emails || [];
                    DeepAnalysisModule.deepAnalysisEmails = deepAnalysisEmails;
                    console.log('Synchronized deepAnalysisEmails with DeepAnalysisModule:', DeepAnalysisModule.deepAnalysisEmails);
                }
            });
            console.log('DeepAnalysisModule initialized');
        }

        if (typeof ConversationsModule !== 'undefined') {
            ConversationsModule.init({
                currentConversationEmails,
                currentConversationThemes,
                setCurrentConversationEmails: (emails) => { 
                    console.log('Setting currentConversationEmails:', emails);
                    currentConversationEmails = emails; 
                },
                setCurrentConversationThemes: (themes) => { 
                    console.log('Setting currentConversationThemes:', themes);
                    currentConversationThemes = themes || [];
                    ConversationsModule.currentConversationThemes = currentConversationThemes;
                    console.log('Synchronized currentConversationThemes with ConversationsModule:', ConversationsModule.currentConversationThemes);
                }
            });
            console.log('ConversationsModule initialized');
        }

        if (typeof DeepConversationAnalysisModule !== 'undefined') {
            DeepConversationAnalysisModule.init({
                deepConversationAnalysisSessionId,
                deepConversationAnalysisEmails,
                setDeepConversationAnalysisSessionId: (id) => { 
                    console.log('Setting deepConversationAnalysisSessionId:', id);
                    deepConversationAnalysisSessionId = id;
                    DeepConversationAnalysisModule.deepConversationAnalysisSessionId = id;
                    console.log('Synchronized deepConversationAnalysisSessionId with DeepConversationAnalysisModule:', DeepConversationAnalysisModule.deepConversationAnalysisSessionId);
                },
                setDeepConversationAnalysisEmails: (emails) => { 
                    console.log('Setting deepConversationAnalysisEmails:', emails);
                    deepConversationAnalysisEmails = emails;
                    DeepConversationAnalysisModule.deepConversationAnalysisEmails = deepConversationAnalysisEmails;
                    console.log('Synchronized deepConversationAnalysisEmails with DeepConversationAnalysisModule:', DeepConversationAnalysisModule.deepConversationAnalysisEmails);
                }
            });
            console.log('DeepConversationAnalysisModule initialized');
        }

        if (typeof DashboardModule !== 'undefined') {
            DashboardModule.init();
            console.log('DashboardModule initialized');
        } else {
            console.error('DashboardModule is not defined');
        }

        if (typeof UserModule !== 'undefined') {
            UserModule.init();
            console.log('UserModule initialized');
        }

        if (typeof ThreadsModule !== 'undefined') {
            ThreadsModule.init();
            console.log('ThreadsModule initialized');
        }

        if (typeof AgattaModule !== 'undefined') {
            AgattaModule.init();
            console.log('AgattaModule initialized');
        }

        // Tab navigation
        document.querySelectorAll('.tab-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const tabId = link.dataset.tab;
                console.log('Tab clicked:', tabId);

                // Hide all tab content and remove active state from all tab links
                document.querySelectorAll('.tab-content').forEach(tab => {
                    tab.classList.remove('active');
                    tab.style.display = 'none'; // Asegurar que los tabs no activos se oculten
                });
                document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));

                // Activate the selected tab link
                link.classList.add('active');

                // Show the selected tab content
                const tabContent = document.getElementById(`${tabId}-section`);
                if (tabContent) {
                    tabContent.classList.add('active');
                    tabContent.style.display = 'block'; // Mostrar el tab seleccionado
                    console.log(`Tab ${tabId} activated`);
                } else {
                    console.error(`Tab content for "${tabId}" not found`);
                }

                // Call the corresponding module's showTab method if it exists
                if (tabId === 'dashboard' && typeof DashboardModule !== 'undefined') {
                    DashboardModule.showTab();
                } else if (tabId === 'user' && typeof UserModule !== 'undefined') {
                    UserModule.showTab();
                } else if (tabId === 'consultas' && typeof SearchModule !== 'undefined') {
                    SearchModule.showTab();
                } else if (tabId === 'themes' && typeof ThemesModule !== 'undefined') {
                    ThemesModule.showTab();
                } else if (tabId === 'deep-analysis' && typeof DeepAnalysisModule !== 'undefined') {
                    DeepAnalysisModule.showTab();
                } else if (tabId === 'conversations' && typeof ConversationsModule !== 'undefined') {
                    ConversationsModule.showTab();
                } else if (tabId === 'conversations-themes' && typeof ConversationsModule !== 'undefined') {
                    ConversationsModule.showThemesTab();
                } else if (tabId === 'deep-conversation-analysis' && typeof DeepConversationAnalysisModule !== 'undefined') {
                    DeepConversationAnalysisModule.showTab();
                } else if (tabId === 'threads' && typeof ThreadsModule !== 'undefined') {
                    ThreadsModule.showTab();
                } else if (tabId === 'agatta' && typeof AgattaModule !== 'undefined') {
                    AgattaModule.showTab();
                } else {
                    console.error(`Module for tab "${tabId}" is not defined`);
                }
            });
        });

        // Modal close handler
        if (closeModal) {
            closeModal.addEventListener('click', () => {
                console.log('Closing modal');
                modal.style.display = 'none';
            });
        }

        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    console.log('Closing modal via background click');
                    modal.style.display = 'none';
                }
            });
        }
    };
});