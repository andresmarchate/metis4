/* Artifact ID: b8d940ed-82df-43f5-abc1-ddefd356b867 */
/* Version: o3p4q5r6-s7t8-u9v0-w1x2-y3z4a5b6c7 */
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
    let currentThemes = []; // Initialize as empty array
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
        setCurrentEmails: (emails) => { currentEmails = emails; },
        setFilterCounts: (counts) => { filterCounts = counts; },
        setTotalPages: (pages) => { totalPages = pages; }
    });

    ThemesModule.init({
        currentThemes,
        setCurrentThemes: (themes) => {
            console.log('Setting currentThemes:', themes);
            currentThemes = themes;
        }
    });

    DeepAnalysisModule.init({
        deepAnalysisSessionId,
        deepAnalysisEmails,
        setDeepAnalysisSessionId: (id) => { deepAnalysisSessionId = id; },
        setDeepAnalysisEmails: (emails) => { deepAnalysisEmails = emails; }
    });

    ConversationsModule.init({
        currentConversationEmails,
        currentConversationThemes,
        setCurrentConversationEmails: (emails) => { currentConversationEmails = emails; },
        setCurrentConversationThemes: (themes) => { currentConversationThemes = themes; }
    });

    DeepConversationAnalysisModule.init({
        deepConversationAnalysisSessionId,
        deepConversationAnalysisEmails,
        setDeepConversationAnalysisSessionId: (id) => { deepConversationAnalysisSessionId = id; },
        setDeepConversationAnalysisEmails: (emails) => { deepConversationAnalysisEmails = emails; }
    });

    // Tab navigation
    document.querySelectorAll('.tab-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = link.dataset.tab;
            console.log('Tab clicked:', tabId);
            // Clear active states
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
            if (tabId === 'consultas') {
                SearchModule.showTab();
            } else if (tabId === 'themes') {
                ThemesModule.showTab();
            } else if (tabId === 'deep-analysis') {
                DeepAnalysisModule.showTab();
            } else if (tabId === 'conversations') {
                ConversationsModule.showTab();
            } else if (tabId === 'conversations-themes') {
                ConversationsModule.showThemesTab();
            } else if (tabId === 'deep-conversation-analysis') {
                DeepConversationAnalysisModule.showTab();
            }
        });
    });

    // Modal close handler
    closeModal.addEventListener('click', () => {
        console.log('Closing modal');
        modal.style.display = 'none';
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            console.log('Closing modal via background click');
            modal.style.display = 'none';
        }
    });
});