/* Artifact ID: d4e5f6g7-8901-2345-d6e7-f89012345678 */
/* Version: a1b2c3d4-5678-9012-a4b5-c67890123456 */
const DeepAnalysisModule = {
    init({ deepAnalysisSessionId, deepAnalysisEmails, setDeepAnalysisSessionId, setDeepAnalysisEmails }) {
        console.log('Initializing DeepAnalysisModule'); // Depuración añadida
        this.deepAnalysisSessionId = deepAnalysisSessionId;
        this.deepAnalysisEmails = deepAnalysisEmails || [];
        this.setDeepAnalysisSessionId = setDeepAnalysisSessionId;
        this.setDeepAnalysisEmails = setDeepAnalysisEmails;

        // DOM elements
        this.deepAnalysisSection = document.getElementById('deep-analysis-section');
        this.themeCheckboxes = document.getElementById('theme-checkboxes');
        this.processDeepAnalysisBtn = document.getElementById('process-deep-analysis');
        this.deepAnalysisInput = document.getElementById('deep-analysis-input');
        this.deepAnalysisPrompt = document.getElementById('deep-analysis-prompt');
        this.submitDeepAnalysisBtn = document.getElementById('submit-deep-analysis');
        this.resetDeepAnalysisContextBtn = document.getElementById('reset-deep-analysis-context');
        this.deepAnalysisResponse = document.getElementById('deep-analysis-response');

        // Debug initialization
        console.log('DeepAnalysisModule init:', {
            deepAnalysisSection: !!this.deepAnalysisSection,
            themeCheckboxes: !!this.themeCheckboxes,
            deepAnalysisResponse: !!this.deepAnalysisResponse,
            processDeepAnalysisBtn: !!this.processDeepAnalysisBtn,
            deepAnalysisInput: !!this.deepAnalysisInput
        });

        // Event listeners
        if (this.processDeepAnalysisBtn) {
            this.processсию

            this.processDeepAnalysisBtn.addEventListener('click', () => this.processDeepAnalysis());
        } else {
            console.warn('processDeepAnalysisBtn not found');
        }
        if (this.submitDeepAnalysisBtn) {
            this.submitDeepAnalysisBtn.addEventListener('click', () => this.submitDeepAnalysis());
        }
        if (this.resetDeepAnalysisContextBtn) {
            this.resetDeepAnalysisContextBtn.addEventListener('click', () => this.resetDeepAnalysisContext());
        }
        
        console.log('DeepAnalysisModule initialized successfully'); // Depuración añadida
    },

    showTab() {
        if (!this.deepAnalysisSection) {
            console.error('deepAnalysisSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Análisis Profundo tab');
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.deepAnalysisSection.classList.add('active');
        const tabLink = document.querySelector('.tab-link[data-tab="deep-analysis"]');
        if (tabLink) {
            tabLink.classList.add('active');
        } else {
            console.warn('Tab link for "deep-analysis" not found');
        }
        this.populateThemeCheckboxes();
    },

    populateThemeCheckboxes(themes = ThemesModule.currentThemes) {
        console.log('Populating theme checkboxes:', themes);
        if (!this.themeCheckboxes) {
            console.error('themeCheckboxes element not found');
            return;
        }
        const selectedThemeIds = Array.from(this.themeCheckboxes.querySelectorAll('input[type="checkbox"]:checked'))
            .map(checkbox => checkbox.value);
        console.log('Preserving selected theme IDs:', selectedThemeIds);

        this.themeCheckboxes.innerHTML = '';
        if (!Array.isArray(themes) || themes.length === 0) {
            console.log('No themes available for checkboxes');
            this.themeCheckboxes.innerHTML = '<p>No hay temas disponibles para seleccionar.</p>';
            return;
        }

        themes.forEach(theme => {
            const checkboxWrapper = document.createElement('label');
            checkboxWrapper.className = 'theme-checkbox';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = theme.theme_id;
            checkbox.dataset.title = theme.title;
            if (selectedThemeIds.includes(theme.theme_id)) {
                checkbox.checked = true;
            }
            const labelText = document.createTextNode(theme.title);
            checkboxWrapper.appendChild(checkbox);
            checkboxWrapper.appendChild(labelText);
            this.themeCheckboxes.appendChild(checkboxWrapper);
            console.log('Added checkbox for theme:', theme.title, 'with ID:', theme.theme_id, 'checked:', checkbox.checked);
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

    async processDeepAnalysis() {
        console.log('Process deep analysis clicked');
        const selectedThemes = Array.from(this.themeCheckboxes.querySelectorAll('input[type="checkbox"]:checked'))
            .map(checkbox => ({
                theme_id: checkbox.value,
                title: checkbox.dataset.title
            }));
        console.log('Selected themes:', selectedThemes);

        if (selectedThemes.length === 0) {
            alert('Por favor, selecciona al menos un tema para analizar.');
            return;
        }

        if (!this.deepAnalysisSection.classList.contains('active')) {
            this.showTab();
        } else {
            console.log('Deep Analysis tab already active, skipping showTab');
        }

        try {
            const response = await fetch('/api/deep_analysis_init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme_ids: selectedThemes.map(theme => theme.theme_id) })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep analysis initialization response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.deepAnalysisSessionId = data.session_id;
            console.log('Local deepAnalysisSessionId set:', this.deepAnalysisSessionId);
            this.setDeepAnalysisSessionId(data.session_id);
            console.log('After external setter, deepAnalysisSessionId:', this.deepAnalysisSessionId);

            this.deepAnalysisEmails = data.email_data || [];
            console.log('Local deepAnalysisEmails set:', this.deepAnalysisEmails);
            this.setDeepAnalysisEmails([...this.deepAnalysisEmails]); // Pass a copy
            console.log('After external setter, deepAnalysisEmails:', this.deepAnalysisEmails);

            if (!this.deepAnalysisResponse) {
                console.error('deepAnalysisResponse element not found');
                alert('Error: No se encontró el contenedor para mostrar los correos.');
                return;
            }

            if (!this.deepAnalysisInput) {
                console.error('deepAnalysisInput element not found');
            } else {
                this.deepAnalysisInput.style.display = 'block';
                console.log('Set deepAnalysisInput display to block');
            }

            // Create table DOM structure
            const tableContainer = document.createElement('div');
            tableContainer.className = 'table-container';
            const table = document.createElement('table');
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            ['Índice', 'Fecha', 'Remitente', 'Destinatario', 'Asunto', 'Resumen'].forEach(header => {
                const th = document.createElement('th');
                th.textContent = header;
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
            table.appendChild(thead);

            const tbody = document.createElement('tbody'); // Corrección: Eliminado el carácter '|' inválido
            if (this.deepAnalysisEmails.length === 0) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 6;
                td.textContent = 'No hay correos disponibles.';
                tr.appendChild(td);
                tbody.appendChild(tr);
            } else {
                this.deepAnalysisEmails.forEach((email, index) => {
                    console.log(`Rendering email ${index}:`, {
                        index: email.index,
                        date: email.date,
                        from: email.from,
                        to: email.to,
                        subject: email.subject,
                        summary: email.summary
                    });
                    const tr = document.createElement('tr');

                    // Index cell
                    const indexCell = document.createElement('td');
                    const indexLink = document.createElement('a');
                    indexLink.href = '#';
                    indexLink.className = 'deep-analysis-email-link';
                    indexLink.dataset.index = UtilsModule.escapeHtml(email.index || 'N/A');
                    indexLink.textContent = UtilsModule.truncateIndex(email.index || 'N/A');
                    indexCell.appendChild(indexLink);
                    tr.appendChild(indexCell);

                    // Date cell
                    const dateCell = document.createElement('td');
                    dateCell.textContent = UtilsModule.escapeHtml(email.date ? new Date(email.date).toLocaleString() : 'N/A');
                    console.log('Rendered date cell:', dateCell.textContent);
                    tr.appendChild(dateCell);

                    // From cell
                    const fromCell = document.createElement('td');
                    fromCell.textContent = UtilsModule.escapeHtml(email.from || 'N/A');
                    console.log('Rendered from cell:', fromCell.textContent);
                    tr.appendChild(fromCell);

                    // To cell
                    const toCell = document.createElement('td');
                    toCell.textContent = UtilsModule.escapeHtml(email.to || 'N/A');
                    console.log('Rendered to cell:', toCell.textContent);
                    tr.appendChild(toCell);

                    // Subject cell
                    const subjectCell = document.createElement('td');
                    subjectCell.textContent = UtilsModule.escapeHtml(email.subject || 'N/A');
                    console.log('Rendered subject cell:', subjectCell.textContent);
                    tr.appendChild(subjectCell);

                    // Summary cell
                    const summaryCell = document.createElement('td');
                    const summaryText = this.formatSummary(email.summary).slice(0, 100); // Corrección: Usar 'this.formatSummary'
                    summaryCell.textContent = summaryText + (email.summary && email.summary.length > 100 ? '...' : '');
                    console.log('Rendered summary cell:', summaryCell.textContent);
                    tr.appendChild(summaryCell);

                    tbody.appendChild(tr);
                });
            }
            table.appendChild(tbody);
            tableContainer.appendChild(table);

            // Assemble response content
            this.deepAnalysisResponse.innerHTML = '';
            const initMessage = document.createElement('p');
            initMessage.textContent = 'Análisis inicializado para los temas seleccionados. Ingresa tu consulta.';
            this.deepAnalysisResponse.appendChild(initMessage);
            const heading = document.createElement('h3');
            heading.textContent = 'Correos disponibles para análisis:';
            this.deepAnalysisResponse.appendChild(heading);
            this.deepAnalysisResponse.appendChild(tableContainer);

            console.log('Table rendered with', tbody.querySelectorAll('tr').length, 'rows');
            this.attachDeepAnalysisEmailListeners();
            console.log('Attached email listeners, table rows:', tbody.querySelectorAll('tr').length);
        } catch (error) {
            console.error('Error initializing deep analysis:', error.message);
            alert(`Error al inicializar análisis profundo: ${error.message}`);
        }
    },

    async submitDeepAnalysis() {
        const prompt = this.deepAnalysisPrompt.value.trim();
        console.log('Submitting deep analysis prompt:', prompt);

        if (!prompt) {
            alert('Por favor, ingresa una consulta válida.');
            return;
        }

        if (!this.deepAnalysisSessionId) {
            console.error('No active session, deepAnalysisSessionId:', this.deepAnalysisSessionId);
            alert('No hay una sesión activa. Por favor, inicializa el análisis primero.');
            return;
        }

        try {
            const response = await fetch('/api/deep_analysis_prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.deepAnalysisSessionId, prompt })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep analysis prompt response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            const indexRegex = /(?:con índice\s+)?\'([0-9a-f]{64})\'/gi;
            console.log('Reasoning text before processing:', data.reasoning);
            const linkedReasoning = data.reasoning.replace(indexRegex, (match, index) => {
                console.log('Found index in reasoning:', index);
                return `<a href="#" class="deep-analysis-email-link" data-index="${index}">${UtilsModule.truncateIndex(index)}</a>`;
            });
            console.log('Processed reasoning with links:', linkedReasoning);

            if (!this.deepAnalysisResponse) {
                console.error('deepAnalysisResponse element not found for prompt response');
                return;
            }

            // Create response DOM structure
            this.deepAnalysisResponse.innerHTML = '';
            const responseHeading = document.createElement('h3');
            responseHeading.textContent = 'Respuesta:';
            this.deepAnalysisResponse.appendChild(responseHeading);
            const responsePara = document.createElement('p');
            responsePara.textContent = UtilsModule.escapeHtml(data.response);
            this.deepAnalysisResponse.appendChild(responsePara);

            const reasoningHeading = document.createElement('h3');
            reasoningHeading.textContent = 'Razonamiento:';
            this.deepAnalysisResponse.appendChild(reasoningHeading);
            const reasoningPara = document.createElement('p');
            reasoningPara.innerHTML = linkedReasoning; // Safe due to regex replacement
            this.deepAnalysisResponse.appendChild(reasoningPara);

            const alternativesHeading = document.createElement('h3');
            alternativesHeading.textContent = 'Alternativas:';
            this.deepAnalysisResponse.appendChild(alternativesHeading);
            const alternativesList = document.createElement('ul');
            (data.alternatives || ['Ninguna']).forEach(alt => {
                const li = document.createElement('li');
                li.textContent = UtilsModule.escapeHtml(alt);
                alternativesList.appendChild(li);
            });
            this.deepAnalysisResponse.appendChild(alternativesList);

            const referencesHeading = document.createElement('h3');
            referencesHeading.textContent = 'Referencias:';
            this.deepAnalysisResponse.appendChild(referencesHeading);
            const refTableContainer = document.createElement('div');
            refTableContainer.className = 'table-container';
            const refTable = document.createElement('table');
            const refThead = document.createElement('thead');
            const refHeaderRow = document.createElement('tr');
            ['Índice', 'Fecha', 'Remitente', 'Destinatario', 'Asunto', 'Resumen'].forEach(header => {
                const th = document.createElement('th');
                th.textContent = header;
                refHeaderRow.appendChild(th);
            });
            refThead.appendChild(refHeaderRow);
            refTable.appendChild(refThead);

            const refTbody = document.createElement('tbody');
            if (!data.references || data.references.length === 0) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 6;
                td.textContent = 'No hay referencias.';
                tr.appendChild(td);
                refTbody.appendChild(tr);
            } else {
                data.references.forEach((ref, index) => {
                    console.log(`Rendering reference ${index}:`, {
                        index: ref.index,
                        date: ref.date,
                        from: ref.from,
                        to: ref.to,
                        subject: ref.subject,
                        summary: ref.summary
                    });
                    const tr = document.createElement('tr');

                    const indexCell = document.createElement('td');
                    const indexLink = document.createElement('a');
                    indexLink.href = '#';
                    indexLink.className = 'deep-analysis-email-link';
                    indexLink.dataset.index = UtilsModule.escapeHtml(ref.index || 'N/A');
                    indexLink.textContent = UtilsModule.truncateIndex(ref.index || 'N/A');
                    indexCell.appendChild(indexLink);
                    tr.appendChild(indexCell);

                    const dateCell = document.createElement('td');
                    dateCell.textContent = UtilsModule.escapeHtml(ref.date ? new Date(ref.date).toLocaleString() : 'N/A');
                    tr.appendChild(dateCell);

                    const fromCell = document.createElement('td');
                    fromCell.textContent = UtilsModule.escapeHtml(ref.from || 'N/A');
                    tr.appendChild(fromCell);

                    const toCell = document.createElement('td');
                    toCell.textContent = UtilsModule.escapeHtml(ref.to || 'N/A');
                    tr.appendChild(toCell);

                    const subjectCell = document.createElement('td');
                    subjectCell.textContent = UtilsModule.escapeHtml(ref.subject || 'N/A');
                    tr.appendChild(subjectCell);

                    const summaryCell = document.createElement('td');
                    const summaryText = this.formatSummary(ref.summary).slice(0, 100);
                    summaryCell.textContent = summaryText + (ref.summary && ref.summary.length > 100 ? '...' : '');
                    tr.appendChild(summaryCell);

                    refTbody.appendChild(tr);
                });
            }
            refTable.appendChild(refTbody);
            refTableContainer.appendChild(refTable);
            this.deepAnalysisResponse.appendChild(refTableContainer);

            this.deepAnalysisPrompt.value = '';
            this.attachDeepAnalysisEmailListeners();
            console.log('Prompt response rendered, table rows:', refTbody.querySelectorAll('tr').length);
        } catch (error) {
            console.error('Error processing deep analysis prompt:', error.message);
            alert(`Error al procesar la consulta: ${error.message}`);
        }
    },

    async resetDeepAnalysisContext() {
        console.log('Resetting deep analysis context');
        if (!this.deepAnalysisSessionId) {
            alert('No hay una sesión activa para resetear.');
            return;
        }

        try {
            const response = await fetch('/api/deep_analysis_reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.deepAnalysisSessionId })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Deep analysis reset response:', data);
            if (data.error) {
                throw new Error(data.error);
            }

            this.deepAnalysisSessionId = null;
            this.setDeepAnalysisSessionId(null);
            this.deepAnalysisEmails = [];
            this.setDeepAnalysisEmails([]);
            if (this.deepAnalysisInput) {
                this.deepAnalysisInput.style.display = 'none';
            }
            this.deepAnalysisPrompt.value = '';
            if (this.deepAnalysisResponse) {
                this.deepAnalysisResponse.innerHTML = '<p>Contexto reseteado. Selecciona nuevos temas para continuar.</p>';
            }
            alert('Contexto reseteado correctamente.');
        } catch (error) {
            console.error('Error resetting deep analysis context:', error.message);
            alert(`Error al resetear el contexto: ${error.message}`);
        }
    },

    attachDeepAnalysisEmailListeners() {
        const links = this.deepAnalysisResponse ? this.deepAnalysisResponse.querySelectorAll('.deep-analysis-email-link') : [];
        console.log('Attaching listeners to', links.length, 'email links');
        links.forEach(link => {
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                const identifier = e.target.dataset.index;
                console.log('Clicked deep analysis email link with identifier:', identifier);
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
                        detailsElement.innerHTML = ''; // Clear previous content
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
                        console.log('Rendered modal with from:', email.from, 'to:', email.to);
                    }
                    const modal = document.getElementById('email-modal');
                    if (modal) {
                        modal.style.display = 'flex';
                    }
                    const notRelevantBtn = document.getElementById('not-relevant');
                    if (notRelevantBtn) {
                        notRelevantBtn.dataset.id = email.message_id || email.index;
                    }
                } catch (err) {
                    console.error('Error fetching email:', err);
                    alert('Error al cargar los detalles del correo: ' + err.message);
                }
            });
        });
    }
};

console.log('DeepAnalysisModule defined:', typeof DeepAnalysisModule !== 'undefined'); // Depuración añadida