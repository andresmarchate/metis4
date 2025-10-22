/* Artifact ID: e5f6g7h8-9012-3456-e7f8-g90123456789 */
/* Version: k1l2m3n4-5678-9012-k3l4-m56789012345 */
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
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.conversationsSection.classList.add('active');
        this.conversationsSection.style.display = 'block';
        const tabLink = document.querySelector('.tab-link[data-tab="conversations"]');
        if (tabLink) tabLink.classList.add('active');
    },

    showThemesTab() {
        if (!this.conversationsThemesSection) {
            console.error('conversationsThemesSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Análisis de Conversaciones tab');
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
            tab.style.display = 'none';
        });
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.conversationsThemesSection.classList.add('active');
        this.conversationsThemesSection.style.display = 'block';
        console.log('Set display to block for conversations-themes-section');
        const tabLink = document.querySelector('.tab-link[data-tab="conversations-themes"]');
        if (tabLink) {
            tabLink.classList.add('active');
            tabLink.scrollIntoView({ behavior: 'smooth', block: 'center' });
            tabLink.focus();
            console.log('Tab "Análisis de Conversaciones" activated, scrolled into view, and focused');
        } else {
            console.error('Tab link for "conversations-themes" not found');
        }
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
                        console.log('Email details fetched:', email);
                        const attachmentsContent = Array.isArray(email.attachments_content)
                            ? email.attachments_content.join('\n')
                            : email.attachments_content || '';
                        const detailsElement = document.getElementById('email-details');
                        if (detailsElement) {
                            detailsElement.innerHTML = '';
                            const createField = (label, value, isBody = false) => {
                                const p = document.createElement('div');
                                p.className = 'email-field';
                                const strong = document.createElement('strong');
                                strong.textContent = label;
                                p.appendChild(strong);
                                if (isBody && value) {
                                    const bodyDiv = document.createElement('div');
                                    bodyDiv.className = 'email-body';
                                    const isHTML = /<[a-zA-Z]+(?:\s+[^>]*)*>[\s\S]*<\/[a-zA-Z]+>/i.test(value) && !value.includes('[image:');
                                    if (isHTML) {
                                        const tempDiv = document.createElement('div');
                                        tempDiv.innerHTML = value;
                                        tempDiv.querySelectorAll('script, [on*], iframe, object, embed').forEach(el => el.remove());
                                        const textContent = tempDiv.innerHTML.replace(/\[image:[^\]]+\]\s*(<[^>]+>)/g, '$1');
                                        tempDiv.innerHTML = textContent;
                                        bodyDiv.appendChild(tempDiv);
                                    } else {
                                        bodyDiv.style.whiteSpace = 'pre-wrap';
                                        let formattedValue = value.replace(/\[image:[^\]]+\]\s*<([^>]+)>/g, '<a href="$1" class="email-link" target="_blank">$1</a>');
                                        formattedValue = formattedValue.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" class="email-link" target="_blank">$1</a>');
                                        bodyDiv.innerHTML = formattedValue;
                                    }
                                    p.appendChild(bodyDiv);
                                } else {
                                    const textNode = document.createTextNode(` ${UtilsModule.escapeHtml(value || 'N/A')}`);
                                    p.appendChild(textNode);
                                }
                                console.log(`Rendered modal field ${label}:`, value);
                                detailsElement.appendChild(p);
                            };
                            createField('Índice:', UtilsModule.truncateIndex(email.index));
                            createField('ID:', email.message_id);
                            createField('De:', email.from);
                            createField('Para:', email.to);
                            createField('Asunto:', email.subject);
                            createField('Fecha:', email.date);
                            createField('Resumen:', this.formatSummary(email.summary));
                            createField('Cuerpo:', email.body, true);
                            createField('Adjuntos:', attachmentsContent);
                        }
                        const modal = document.getElementById('email-modal');
                        if (modal) {
                            modal.style.display = 'flex';
                            console.log('Email modal displayed successfully');
                        }
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
            console.log('Sending theme analysis request to /api/analyze_themes with email IDs:', emailIds);
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
            console.log('Received theme analysis response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.renderConversationThemes(data.themes || []);
            console.log('Themes rendered, currentConversationThemes updated:', this.currentConversationThemes);
            if (this.errorMessageConversations) this.errorMessageConversations.style.display = 'none';
            this.showThemesTab();
            DeepConversationAnalysisModule.populateConversationThemeCheckboxes();
            console.log('Deep conversation analysis checkboxes populated with themes:', this.currentConversationThemes);
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

    renderConversationThemes(themes) {
        console.log('Starting renderConversationThemes with themes:', themes);
        if (!this.conversationsThemesList) {
            console.error('conversationsThemesList is undefined, cannot render themes');
            return;
        }
        try {
            this.conversationsThemesList.innerHTML = '';
            if (!Array.isArray(themes) || themes.length === 0) {
                console.log('No conversation themes to render');
                this.conversationsThemesList.innerHTML = '<p id="no-results-message">No se identificaron temas.</p>';
                this.setCurrentConversationThemes([]);
                return;
            }

            this.setCurrentConversationThemes(themes);

            themes.forEach(theme => {
                console.log('Rendering theme:', theme);
                let summaryHtml = '';
                if (typeof theme.summary === 'object' && theme.summary.tema) {
                    summaryHtml = `<ul class="theme-summary">
                        <li><strong>Tema:</strong> ${UtilsModule.escapeHtml(theme.summary.tema)}</li>
                        <li><strong>Involucrados:</strong> ${UtilsModule.escapeHtml(theme.summary.involucrados.join(', '))}</li>
                        <li><strong>Historia:</strong> ${UtilsModule.escapeHtml(theme.summary.historia)}</li>
                        <li><strong>Próximos pasos:</strong> ${UtilsModule.escapeHtml(theme.summary.proximos_pasos)}</li>
                        <li><strong>Puntos claves:</strong>
                            <ul>
                                ${theme.summary.puntos_claves.map(point => `<li>${UtilsModule.escapeHtml(point)}</li>`).join('')}
                            </ul>
                        </li>
                    </ul>`;
                } else if (Array.isArray(theme.summary)) {
                    summaryHtml = `<ul class="theme-summary">${theme.summary.map(point => `<li>${UtilsModule.escapeHtml(point)}</li>`).join('')}</ul>`;
                } else if (typeof theme.summary === 'string') {
                    const points = theme.summary.split(/[\n,]+/).map(p => p.trim()).filter(p => p);
                    if (points.length > 1) summaryHtml = `<ul class="theme-summary">${points.map(point => `<li>${UtilsModule.escapeHtml(point)}</li>`).join('')}</ul>`;
                    else summaryHtml = `<p class="theme-summary">${UtilsModule.escapeHtml(theme.summary || 'No hay resumen disponible.')}</p>`;
                } else {
                    summaryHtml = `<p class="theme-summary">No hay resumen disponible.</p>`;
                }

                const detail = document.createElement('details');
                const summary = document.createElement('summary');
                const similarityScore = theme.similarity_score ? `Similitud: ${(theme.similarity_score * 100).toFixed(1)}%` : 'Similitud: N/A';
                summary.innerHTML = `<strong>${UtilsModule.escapeHtml(theme.title || 'Sin título')}</strong> (${theme.emails?.length || 0} correos, Estado: ${UtilsModule.escapeHtml(theme.status || 'N/A')}, ${similarityScore})`;
                detail.appendChild(summary);

                const summaryHeading = document.createElement('h3');
                summaryHeading.textContent = 'Resumen del Tema';
                detail.appendChild(summaryHeading);

                const summaryDiv = document.createElement('div');
                summaryDiv.innerHTML = summaryHtml;
                detail.appendChild(summaryDiv);

                if (Array.isArray(theme.emails) && theme.emails.length > 0) {
                    const tableContainer = document.createElement('div');
                    tableContainer.className = 'table-container';
                    
                    const emailTable = document.createElement('table');
                    emailTable.className = 'email-table';

                    const thead = document.createElement('thead');
                    const headerRow = document.createElement('tr');
                    ['Índice', 'Fecha', 'Remitente', 'Destinatario', 'Asunto', 'Descripción'].forEach(header => {
                        const th = document.createElement('th');
                        th.textContent = header;
                        headerRow.appendChild(th);
                    });
                    thead.appendChild(headerRow);
                    emailTable.appendChild(thead);

                    const tbody = document.createElement('tbody');
                    theme.emails.forEach(email => {
                        console.log('Rendering theme email:', { 
                            index: email.index, 
                            message_id: email.message_id, 
                            from: email.from, 
                            to: email.to 
                        });
                        const row = document.createElement('tr');

                        const indexCell = document.createElement('td');
                        const indexLink = document.createElement('a');
                        const index = email.index && email.index !== 'N/A' ? email.index : email.message_id;
                        indexLink.href = '#';
                        indexLink.className = 'theme-email-link';
                        indexLink.dataset.index = UtilsModule.escapeHtml(index);
                        indexLink.textContent = UtilsModule.truncateIndex(index);
                        indexCell.appendChild(indexLink);
                        console.log('Rendered theme index cell:', indexCell.textContent);
                        row.appendChild(indexCell);

                        const dateCell = document.createElement('td');
                        dateCell.textContent = UtilsModule.escapeHtml(email.date ? new Date(email.date).toLocaleString() : 'N/A');
                        console.log('Rendered theme date cell:', dateCell.textContent);
                        row.appendChild(dateCell);

                        const fromCell = document.createElement('td');
                        fromCell.textContent = UtilsModule.escapeHtml(email.from || 'N/A');
                        console.log('Rendered theme from cell:', fromCell.textContent);
                        row.appendChild(fromCell);

                        const toCell = document.createElement('td');
                        toCell.textContent = UtilsModule.escapeHtml(email.to || 'N/A');
                        console.log('Rendered theme to cell:', toCell.textContent);
                        row.appendChild(toCell);

                        const subjectCell = document.createElement('td');
                        subjectCell.textContent = UtilsModule.escapeHtml(email.subject || 'N/A');
                        console.log('Rendered theme subject cell:', subjectCell.textContent);
                        row.appendChild(subjectCell);

                        const descCell = document.createElement('td');
                        const descText = email.description?.slice(0, 100) || '';
                        descCell.textContent = UtilsModule.escapeHtml(descText) + (email.description?.length > 100 ? '...' : '');
                        console.log('Rendered theme description cell:', descCell.textContent);
                        row.appendChild(descCell);

                        tbody.appendChild(row);
                    });
                    emailTable.appendChild(tbody);
                    tableContainer.appendChild(emailTable);
                    detail.appendChild(tableContainer);
                }

                this.conversationsThemesList.appendChild(detail);

                detail.querySelectorAll('.theme-email-link').forEach(link => {
                    link.addEventListener('click', async (e) => {
                        e.preventDefault();
                        const identifier = e.target.dataset.index;
                        console.log('Clicked theme email link with identifier:', identifier);
                        if (!identifier || identifier === 'N/A') {
                            console.error('No valid identifier found for link:', e.target);
                            alert('Identificador de correo no válido.');
                            return;
                        }
                        try {
                            console.log('Fetching email details for identifier:', identifier);
                            const response = await fetch(`/api/email?index=${encodeURIComponent(identifier)}`);
                            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                            const email = await response.json();
                            console.log('Email details:', email);
                            const attachmentsContent = Array.isArray(email.attachments_content)
                                ? email.attachments_content.join('\n')
                                : email.attachments_content || '';
                            const detailsElement = document.getElementById('email-details');
                            if (detailsElement) {
                                detailsElement.innerHTML = '';
                                const createField = (label, value, isBody = false) => {
                                    const p = document.createElement('div');
                                    p.className = 'email-field';
                                    const strong = document.createElement('strong');
                                    strong.textContent = label;
                                    p.appendChild(strong);
                                    if (isBody && value) {
                                        const bodyDiv = document.createElement('div');
                                        bodyDiv.className = 'email-body';
                                        const isHTML = /<[a-zA-Z]+(?:\s+[^>]*)*>[\s\S]*<\/[a-zA-Z]+>/i.test(value) && !value.includes('[image:');
                                        if (isHTML) {
                                            const tempDiv = document.createElement('div');
                                            tempDiv.innerHTML = value;
                                            tempDiv.querySelectorAll('script, [on*], iframe, object, embed').forEach(el => el.remove());
                                            const textContent = tempDiv.innerHTML.replace(/\[image:[^\]]+\]\s*(<[^>]+>)/g, '$1');
                                            tempDiv.innerHTML = textContent;
                                            bodyDiv.appendChild(tempDiv);
                                        } else {
                                            bodyDiv.style.whiteSpace = 'pre-wrap';
                                            let formattedValue = value.replace(/\[image:[^\]]+\]\s*<([^>]+)>/g, '<a href="$1" class="email-link" target="_blank">$1</a>');
                                            formattedValue = formattedValue.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" class="email-link" target="_blank">$1</a>');
                                            bodyDiv.innerHTML = formattedValue;
                                        }
                                        p.appendChild(bodyDiv);
                                    } else {
                                        const textNode = document.createTextNode(` ${UtilsModule.escapeHtml(value || 'N/A')}`);
                                        p.appendChild(textNode);
                                    }
                                    console.log(`Rendered modal field ${label}:`, value);
                                    detailsElement.appendChild(p);
                                };
                                createField('Índice:', email.index || 'N/A');
                                createField('ID:', email.message_id || 'N/A');
                                createField('De:', email.from || 'N/A');
                                createField('Para:', email.to || 'N/A');
                                createField('Asunto:', email.subject || 'N/A');
                                createField('Fecha:', email.date || 'N/A');
                                createField('Resumen:', this.formatSummary(email.summary));
                                createField('Cuerpo:', email.body || 'N/A', true);
                                createField('Adjuntos:', attachmentsContent || 'N/A');
                            } else {
                                console.error('email-details element not found');
                                alert('Error: No se encontró el contenedor para los detalles del correo.');
                            }
                            const modal = document.getElementById('email-modal');
                            if (modal) modal.style.display = 'flex';
                            else console.error('email-modal element not found');
                            const notRelevantBtn = document.getElementById('not-relevant');
                            if (notRelevantBtn) notRelevantBtn.dataset.id = email.message_id || email.index;
                        } catch (err) {
                            console.error('Error fetching email:', err);
                            alert('Error al cargar los detalles del correo: ' + err.message);
                        }
                    });
                });
            });
            console.log('All themes rendered successfully');
            this.showThemesTab();
        } catch (error) {
            console.error('Error rendering conversation themes:', error);
            this.conversationsThemesList.innerHTML = '<p id="error-message">Error al renderizar temas: ' + UtilsModule.escapeHtml(error.message) + '</p>';
            this.showThemesTab();
        }
    },

    setCurrentConversationThemes(themes) {
        console.log('Setting currentConversationThemes:', themes);
        this.currentConversationThemes = themes || [];
        if (this.setCurrentConversationThemes) {
            this.setCurrentConversationThemes([...this.currentConversationThemes]);
            console.log('After external setter, currentConversationThemes:', this.currentConversationThemes);
        }
    }
};