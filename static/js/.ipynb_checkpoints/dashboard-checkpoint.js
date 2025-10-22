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

    // Initialize modules
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

    DashboardModule.init();
    console.log('DashboardModule initialized');

    UserModule.init();
    console.log('UserModule initialized');

    ThreadsModule.init();
    console.log('ThreadsModule initialized');

    AgattaModule.init();
    console.log('AgattaModule initialized');

    // Tab navigation
    document.querySelectorAll('.tab-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = link.dataset.tab;
            console.log('Tab clicked:', tabId);

            // Hide all tab content and remove active state from all tab links
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));

            // Activate the selected tab link
            link.classList.add('active');

            // Show the selected tab content
            if (tabId === 'dashboard') {
                console.log('Activating Dashboard tab');
                DashboardModule.showTab();
            } else if (tabId === 'user') {
                console.log('Activating User tab');
                UserModule.showTab();
            } else if (tabId === 'consultas') {
                console.log('Activating Consultas tab');
                SearchModule.showTab();
            } else if (tabId === 'themes') {
                console.log('Activating Themes tab');
                ThemesModule.showTab();
            } else if (tabId === 'deep-analysis') {
                console.log('Activating Deep Analysis tab');
                DeepAnalysisModule.showTab();
            } else if (tabId === 'conversations') {
                console.log('Activating Conversations tab');
                ConversationsModule.showTab();
            } else if (tabId === 'conversations-themes') {
                console.log('Activating Conversations Themes tab');
                ConversationsModule.showThemesTab();
            } else if (tabId === 'deep-conversation-analysis') {
                console.log('Activating Deep Conversation Analysis tab');
                DeepConversationAnalysisModule.showTab();
            } else if (tabId === 'threads') {
                console.log('Activating Threads tab');
                ThreadsModule.showTab();
            } else if (tabId === 'agatta') {
                console.log('Activating AGATTA tab');
                AgattaModule.showTab();
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
});