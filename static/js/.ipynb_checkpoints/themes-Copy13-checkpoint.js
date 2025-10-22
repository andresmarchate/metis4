/* Version: u2v3w4x5-6789-0123-u4v5-w67890123456 */
const ThemesModule = {
    init({ currentThemes, setCurrentThemes }) {
        this.currentThemes = currentThemes || [];
        this.setCurrentThemes = setCurrentThemes;
        this.themesSection = document.getElementById('themes-section');
        this.themesList = document.getElementById('themes-list');

        console.log('ThemesModule init: themesSection found:', !!this.themesSection, 'themesList found:', !!this.themesList);

        if (!this.themesSection) console.error('themesSection element not found');
        if (!this.themesList) console.error('themesList element not found');

        this.addResetCacheButton();
    },

    showTab() {
        if (!this.themesSection) {
            console.error('themesSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Análisis de Temas tab');
        try {
            const tabContents = document.querySelectorAll('.tab-content');
            if (!tabContents.length) console.warn('No .tab-content elements found');
            else tabContents.forEach(element => element.classList.remove('active'));

            const tabLinks = document.querySelectorAll('.tab-link');
            if (!tabLinks.length) console.warn('No .tab-link elements found');
            else tabLinks.forEach(link => link.classList.remove('active'));

            this.themesSection.classList.add('active');
            const tabLink = document.querySelector('.tab-link[data-tab="themes"]');
            if (tabLink) tabLink.classList.add('active');
            else console.warn('Tab link for "themes" not found');
        } catch (error) {
            console.error('Error in showTab:', error);
        }
    },

    setCurrentThemes(themes) {
        console.log('Setting currentThemes:', themes);
        this.currentThemes = themes || [];
        if (this.setCurrentThemes) {
            this.setCurrentThemes([...this.currentThemes]);
            console.log('After external setter, currentThemes:', this.currentThemes);
        }
        console.log('Updated currentThemes:', this.currentThemes);
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

    addResetCacheButton() {
        const resetButton = document.createElement('button');
        resetButton.textContent = 'Resetear caché de temas';
        resetButton.className = 'reset-cache-btn';
        resetButton.style.margin = '10px';
        resetButton.addEventListener('click', async () => {
            console.log('Reset cache button clicked');
            const emailIds = this.currentThemes.flatMap(theme => 
                theme.emails.map(email => String(email.index))
            ).filter(id => id && id !== 'N/A');
            console.log('Email IDs (indices) to send for cache reset:', emailIds);
            if (!emailIds.length) {
                console.warn('No valid email indices available to reset cache');
                alert('No hay temas actuales con índices válidos para resetear el caché.');
                return;
            }
            try {
                const response = await fetch('/api/clear_theme_cache', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ emailIds })
                });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
                }
                const result = await response.json();
                console.log('Cache reset response:', result);
                alert('Caché de temas reseteado exitosamente.');
                this.renderThemes(this.currentThemes);
            } catch (error) {
                console.error('Error resetting theme cache:', error);
                alert('Error al resetear el caché: ' + error.message);
            }
        });
        if (this.themesSection) this.themesSection.insertBefore(resetButton, this.themesList);
    },

    renderThemes(themes, container = this.themesList) {
        console.log('Rendering themes:', themes);
        if (!container) {
            console.error('Container is undefined, cannot render themes');
            return;
        }
        try {
            container.innerHTML = '';
            if (!Array.isArray(themes) || themes.length === 0) {
                console.log('No themes to render');
                container.innerHTML = '<p id="no-results-message">No se identificaron temas.</p>';
                this.setCurrentThemes([]);
                if (container === this.themesList) {
                    DeepAnalysisModule.populateThemeCheckboxes([]);
                    this.showTab();
                } else {
                    ConversationsModule.populateConversationThemeCheckboxes();
                    ConversationsModule.showThemesTab();
                }
                return;
            }

            if (container === this.themesList) this.setCurrentThemes(themes);
            else ConversationsModule.setCurrentConversationThemes(themes);

            themes.forEach(theme => {
                console.log('Processing theme:', theme);
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
                summary.innerHTML = `<strong>${UtilsModule.escapeHtml(theme.title || 'Sin título')}</strong> (${theme.emails?.length || 0} correos, Estado: ${UtilsModule.escapeHtml(theme.status || 'N/A')})`;
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

                container.appendChild(detail);

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
                                const createField = (label, value) => {
                                    const p = document.createElement('p');
                                    const strong = document.createElement('strong');
                                    strong.textContent = label;
                                    p.appendChild(strong);
                                    const textNode = document.createTextNode(` ${UtilsModule.escapeHtml(value || 'N/A')}`);
                                    p.appendChild(textNode);
                                    console.log(`Rendered modal field ${label}:`, value, 'Rendered text:', textNode.nodeValue);
                                    detailsElement.appendChild(p);
                                };
                                createField('Índice:', email.index || 'N/A');
                                createField('ID:', email.message_id || 'N/A');
                                createField('De:', email.from || 'N/A');
                                createField('Para:', email.to || 'N/A');
                                createField('Asunto:', email.subject || 'N/A');
                                createField('Fecha:', email.date || 'N/A');
                                createField('Resumen:', this.formatSummary(email.summary));
                                createField('Cuerpo:', email.body || 'N/A');
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

            if (container === this.themesList) this.showTab();
            else ConversationsModule.showThemesTab();
        } catch (error) {
            console.error('Error rendering themes:', error);
            container.innerHTML = '<p id="error-message">Error al renderizar temas: ' + UtilsModule.escapeHtml(error.message) + '</p>';
            if (container === this.themesList) this.showTab();
            else ConversationsModule.showThemesTab();
        }
    }
};