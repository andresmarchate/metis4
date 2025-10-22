/* Artifact ID: e5f6g7h8-9012-3456-e7f8-g90123456789 */
/* Version: j0k1l2m3-4567-8901-j2k3-l45678901234 */
const ConversationsModule = {
    init({ currentConversationEmails, currentConversationThemes, setCurrentConversationEmails, setCurrentConversationThemes }) {
        this.currentConversationEmails = currentConversationEmails || [];
        this.currentConversationThemes = currentConversationThemes || [];
        this.setCurrentConversationEmails = setCurrentConversationEmails;
        this.setCurrentConversationThemes = setCurrentConversationThemes;

        // DOM elements
        this.conversationsSection = document.getElementById('conversations-section');
        this.conversationsForm = document.getElementById('conversations-form');
        this.email1Input = document.getElementById('email1');
        this.email2Input = document.getElementById('email2');
        this.startDateInput = document.getElementById('start-date');
        this.endDateInput = document.getElementById('end-date');
        this.errorMessageConversations = document.getElementById('error-message-conversations');
        this.conversationsCount = document.getElementById('conversations-count');
        this.conversationsTable = document.getElementById('conversations-table');
        this.conversationsBody = document.getElementById('conversations-body');
        this.analyzeConversationThemesBtn = document.getElementById('analyze-conversation-themes');
        this.conversationsThemesSection = document.getElementById('conversations-themes-section');
        this.conversationsThemesList = document.getElementById('conversations-themes-list');

        // Debug initialization
        console.log('ConversationsModule init:', {
            conversationsSection: !!this.conversationsSection,
            conversationsForm: !!this.conversationsForm,
            email1Input: !!this.email1Input,
            email2Input: !!this.email2Input,
            startDateInput: !!this.startDateInput,
            endDateInput: !!this.endDateInput,
            errorMessageConversations: !!this.errorMessageConversations,
            conversationsCount: !!this.conversationsCount,
            conversationsTable: !!this.conversationsTable,
            conversationsBody: !!this.conversationsBody,
            analyzeConversationThemesBtn: !!this.analyzeConversationThemesBtn,
            conversationsThemesSection: !!this.conversationsThemesSection,
            conversationsThemesList: !!this.conversationsThemesList
        });

        // Validate DOM elements
        if (!this.conversationsBody) console.error('conversationsBody element not found');
        if (!this.errorMessageConversations) console.error('errorMessageConversations element not found');
        if (!this.conversationsForm) console.warn('conversationsForm not found');

        // Initialize autocomplete
        if (this.email1Input) this.initializeAutocomplete(this.email1Input);
        if (this.email2Input) this.initializeAutocomplete(this.email2Input);

        // Event listeners
        if (this.conversationsForm) {
            this.conversationsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                console.log('Conversation form submitted');
                this.performConversationSearch();
            });
        }

        if (this.analyzeConversationThemesBtn) {
            this.analyzeConversationThemesBtn.addEventListener('click', () => this.analyzeConversationThemes());
        }
    },

    showTab() {
        if (!this.conversationsSection) {
            console.error('conversationsSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Conversaciones tab');
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.conversationsSection.classList.add('active');
        const tabLink = document.querySelector('.tab-link[data-tab="conversations"]');
        if (tabLink) tabLink.classList.add('active');
    },

    showThemesTab() {
        if (!this.conversationsThemesSection) {
            console.error('conversationsThemesSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Análisis de Conversaciones tab');
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.conversationsThemesSection.classList.add('active');
        const tabLink = document.querySelector('.tab-link[data-tab="conversations-themes"]');
        if (tabLink) tabLink.classList.add('active');
    },

    initializeAutocomplete(inputElement) {
        if (!inputElement) {
            console.warn('Input element for autocomplete is undefined');
            return;
        }
        $(inputElement).autocomplete({
            source: (request, response) => {
                console.log('Fetching autocomplete suggestions for:', request.term);
                fetch(`/api/email_addresses?prefix=${encodeURIComponent(request.term)}&limit=50`)
                    .then(res => {
                        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                        return res.json();
                    })
                    .then(data => {
                        console.log('Autocomplete suggestions received:', data.addresses);
                        response(data.addresses || []);
                    })
                    .catch(err => {
                        console.error('Error fetching autocomplete suggestions:', err);
                        if (this.errorMessageConversations) {
                            this.errorMessageConversations.textContent = 'Error al cargar sugerencias de correo.';
                            this.errorMessageConversations.style.display = 'block';
                        }
                        response([]);
                    });
            },
            minLength: 2,
            select: (event, ui) => {
                console.log('Selected autocomplete item:', ui.item.value);
                inputElement.value = ui.item.value;
                return false;
            }
        });
    },

    // Utility to parse summary field
    formatSummary(summary) {
        if (!summary || summary === 'N/A') return 'N/A';
        try {
            if (summary.startsWith('{') && summary.includes('"summary"')) {
                const parsed = JSON.parse(summary);
                return UtilsModule.escapeHtml(parsed.summary || summary);
            }
        } catch (error) {
            console.warn('Failed to parse summary as JSON:', summary, error);
        }
        return UtilsModule.escapeHtml(summary);
    },

    async performConversationSearch() {
        const email1 = this.email1Input?.value.trim();
        const email2 = this.email2Input?.value.trim();
        const startDate = this.startDateInput?.value;
        const endDate = this.endDateInput?.value;

        console.log('Performing conversation search:', { email1, email2, startDate, endDate });

        if (!this.conversationsBody || !this.errorMessageConversations || !this.conversationsTable || !this.conversationsCount || !this.analyzeConversationThemesBtn || !this.conversationsThemesList) {
            console.error('Required DOM elements missing', {
                conversationsBody: !!this.conversationsBody,
                errorMessageConversations: !!this.errorMessageConversations,
                conversationsTable: !!this.conversationsTable,
                conversationsCount: !!this.conversationsCount,
                analyzeConversationThemesBtn: !!this.analyzeConversationThemesBtn,
                conversationsThemesList: !!this.conversationsThemesList
            });
            alert('Error: No se encontraron elementos necesarios en la página.');
            return;
        }

        if (!email1 || !email2 || !startDate || !endDate) {
            console.warn('Missing required conversation fields');
            this.errorMessageConversations.textContent = 'Por favor, completa todos los campos.';
            this.errorMessageConversations.style.display = 'block';
            return;
        }

        this.errorMessageConversations.style.display = 'none';
        this.conversationsBody.innerHTML = '';
        this.conversationsTable.style.display = 'none';
        this.conversationsCount.style.display = 'none';
        this.analyzeConversationThemesBtn.style.display = 'none';
        this.conversationsThemesList.innerHTML = '';

        try {
            console.log('Sending POST request to /api/conversation_emails', { email1, email2, startDate, endDate });
            const response = await fetch('/api/conversation_emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email1,
                    email2,
                    start_date: startDate,
                    end_date: endDate
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Conversation search response:', data);

            if (data.error) {
                throw new Error(data.error);
            }

            const results = data.results || [];
            const totalResults = data.totalResults || 0;

            if (results.length === 0) {
                console.log('No conversation emails found');
                this.errorMessageConversations.textContent = 'No se encontraron correos para los criterios seleccionados.';
                this.errorMessageConversations.style.display = 'block';
                return;
            }

            this.conversationsCount.textContent = `Se encontraron ${totalResults} correos`;
            this.conversationsCount.style.display = 'block';
            this.conversationsTable.style.display = 'table';
            this.analyzeConversationThemesBtn.style.display = 'block';

            const emailData = results.map(result => ({
                message_id: result.message_id,
                index: result.index
            }));
            console.log('Mapped email data:', emailData);
            const filteredEmails = emailData.filter(email => email.index || email.message_id);
            console.log('Filtered email data:', filteredEmails);

            this.currentConversationEmails = filteredEmails;
            console.log('Local currentConversationEmails set:', this.currentConversationEmails);
            this.setCurrentConversationEmails(filteredEmails);
            console.log('After external setter, currentConversationEmails:', this.currentConversationEmails);

            results.forEach(result => {
                console.log('Rendering conversation result:', {
                    index: result.index,
                    message_id: result.message_id,
                    from: result.from,
                    to: result.to
                });
                const row = document.createElement('tr');

                const indexCell = document.createElement('td');
                const indexLink = document.createElement('a');
                indexLink.href = '#';
                indexLink.className = 'index-link';
                indexLink.dataset.index = UtilsModule.escapeHtml(result.index || 'N/A');
                indexLink.textContent = UtilsModule.truncateIndex(result.index || 'N/A');
                indexCell.appendChild(indexLink);
                row.appendChild(indexCell);

                const dateCell = document.createElement('td');
                dateCell.textContent = UtilsModule.escapeHtml(result.date ? new Date(result.date).toLocaleString() : 'N/A');
                console.log('Rendered date cell:', dateCell.textContent);
                row.appendChild(dateCell);

                const fromCell = document.createElement('td');
                fromCell.textContent = UtilsModule.escapeHtml(result.from || 'N/A');
                console.log('Rendered from cell:', fromCell.textContent);
                row.appendChild(fromCell);

                const toCell = document.createElement('td');
                toCell.textContent = UtilsModule.escapeHtml(result.to || 'N/A');
                console.log('Rendered to cell:', toCell.textContent);
                row.appendChild(toCell);

                const subjectCell = document.createElement('td');
                subjectCell.textContent = UtilsModule.escapeHtml(result.subject || '');
                console.log('Rendered subject cell:', subjectCell.textContent);
                row.appendChild(subjectCell);

                const descCell = document.createElement('td');
                const descText = (result.description || '').slice(0, 100);
                descCell.textContent = UtilsModule.escapeHtml(descText) + (result.description && result.description.length > 100 ? '...' : '');
                console.log('Rendered description cell:', descCell.textContent);
                row.appendChild(descCell);

                this.conversationsBody.appendChild(row);
            });

            this.conversationsBody.querySelectorAll('.index-link').forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = e.target.dataset.index;
                    console.log('Clicked conversation index link with identifier:', identifier);
                    if (!identifier || identifier === 'N/A') {
                        console.error('No valid identifier found for link:', e.target);
                        alert('Identificador de correo no válido.');
                        return;
                    }
                    try {
                        console.log('Fetching email details for identifier:', identifier);
                        const response = await fetch(`/api/email?index=${encodeURIComponent(identifier)}`);
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const email = await response.json();
                        console.log('Email details:', email);
                        const attachmentsContent = Array.isArray(email.attachments_content)
                            ? email.attachments_content.join('\n')
                            : email.attachments_content || '';
                        const detailsElement = document.getElementById('email-details');
                        if (detailsElement) {
                            detailsElement.innerHTML = '';
                            const createField = (label, value) => {
                                const p = document.createElement('p');
                                const strong = document.createElement('strong');
                                strong.textContent = label;
                                p.appendChild(strong);
                                p.appendChild(document.createTextNode(` ${UtilsModule.escapeHtml(value || 'N/A')}`));
                                console.log(`Rendered modal field ${label}:`, value);
                                detailsElement.appendChild(p);
                            };
                            createField('Índice:', email.index);
                            createField('ID:', email.message_id);
                            createField('De:', email.from);
                            createField('Para:', email.to);
                            createField('Asunto:', email.subject);
                            createField('Fecha:', email.date);
                            createField('Resumen:', this.formatSummary(email.summary));
                            createField('Cuerpo:', email.body);
                            createField('Adjuntos:', attachmentsContent);
                        }
                        const modal = document.getElementById('email-modal');
                        if (modal) modal.style.display = 'flex';
                        const notRelevantBtn = document.getElementById('not-relevant');
                        if (notRelevantBtn) notRelevantBtn.dataset.id = email.message_id || email.index;
                    } catch (err) {
                        console.error('Error fetching email:', err);
                        alert('Error al cargar los detalles del correo: ' + err.message);
                    }
                });
            });
        } catch (err) {
            console.error('Error during conversation search:', err);
            this.errorMessageConversations.textContent = 'Error al buscar correos: ' + err.message;
            this.errorMessageConversations.style.display = 'block';
        }
    },

    async analyzeConversationThemes() {
        console.log('Analyze conversation themes clicked', { currentConversationEmails: this.currentConversationEmails });
        if (!this.currentConversationEmails || !Array.isArray(this.currentConversationEmails) || this.currentConversationEmails.length === 0) {
            console.warn('No valid conversation emails to analyze', { currentConversationEmails: this.currentConversationEmails });
            if (this.errorMessageConversations) {
                this.errorMessageConversations.textContent = 'No hay correos válidos para analizar temas.';
                this.errorMessageConversations.style.display = 'block';
            }
            return;
        }

        const emailIds = this.currentConversationEmails.map(email => email.index || email.message_id).filter(id => id && id !== 'N/A');
        console.log('Extracted email IDs for theme analysis:', emailIds);
        if (emailIds.length === 0) {
            console.warn('No valid email identifiers for theme analysis', { emailIds });
            if (this.errorMessageConversations) {
                this.errorMessageConversations.textContent = 'No hay identificadores de correos válidos para analizar.';
                this.errorMessageConversations.style.display = 'block';
            }
            return;
        }

        try {
            console.log('Sending theme analysis request for conversation emails:', emailIds);
            const response = await fetch('/api/analyze_themes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email_ids: emailIds })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error: ${response.status}` }));
                throw new Error(errorData.error || `HTTP error: ${response.status}`);
            }

            const data = await response.json();
            console.log('Conversation theme analysis response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            ThemesModule.renderThemes(data.themes || [], this.conversationsThemesList);
            if (this.errorMessageConversations) this.errorMessageConversations.style.display = 'none';
            this.showThemesTab();
            // Populate Deep Conversation Analysis checkboxes
            DeepConversationAnalysisModule.populateConversationThemeCheckboxes();
        } catch (error) {
            console.error('Error analyzing conversation themes:', error.message);
            if (this.errorMessageConversations) {
                this.errorMessageConversations.textContent = `Error al analizar temas: ${error.message}`;
                this.errorMessageConversations.style.display = 'block';
            }
            if (this.conversationsThemesList) {
                this.conversationsThemesList.innerHTML = '<p id="no-results-message">No se identificaron temas.</p>';
            }
        }
    },

    populateConversationThemeCheckboxes() {
        DeepConversationAnalysisModule.populateConversationThemeCheckboxes();
    }
};