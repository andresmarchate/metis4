/* Artifact ID: eed337c9-ce63-419b-a512-99ffcb16f654 */
/* Version: e6f7g8h9-0123-4567-e8f9-g01234567890 */
const ThemesModule = {
    init({ currentThemes, setCurrentThemes }) {
        this.currentThemes = currentThemes || []; // Initialize as empty array
        this.setCurrentThemes = setCurrentThemes;
        this.themesSection = document.getElementById('themes-section');
        this.themesList = document.getElementById('themes-list');

        // Debug initialization
        console.log('ThemesModule init: themesSection found:', !!this.themesSection, 'themesList found:', !!this.themesList);
    },

    showTab() {
        if (!this.themesSection) {
            console.error('themesSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Análisis de Temas tab');
        // Clear other active tabs
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.themesSection.classList.add('active');
        const tabLink = document.querySelector('.tab-link[data-tab="themes"]');
        if (tabLink) {
            tabLink.classList.add('active');
        } else {
            console.warn('Tab link for "themes" not found');
        }
        DeepAnalysisModule.populateThemeCheckboxes();
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
                    DeepAnalysisModule.populateThemeCheckboxes();
                    this.showTab();
                } else {
                    ConversationsModule.populateConversationThemeCheckboxes();
                    ConversationsModule.showThemesTab();
                }
                return;
            }

            if (container === this.themesList) {
                this.setCurrentThemes(themes);
                console.log('Updated currentThemes:', this.currentThemes);
            } else {
                ConversationsModule.setCurrentConversationThemes(themes);
            }

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
                    if (points.length > 1) {
                        summaryHtml = `<ul class="theme-summary">${points.map(point => `<li>${UtilsModule.escapeHtml(point)}</li>`).join('')}</ul>`;
                    } else {
                        summaryHtml = `<p class="theme-summary">${UtilsModule.escapeHtml(theme.summary || 'No hay resumen disponible.')}</p>`;
                    }
                } else {
                    summaryHtml = `<p class="theme-summary">No hay resumen disponible.</p>`;
                }

                const detail = document.createElement('details');
                detail.innerHTML = `
                    <summary>
                        <strong>${UtilsModule.escapeHtml(theme.title || 'Sin título')}</strong> (${theme.emails?.length || 0} correos, Estado: ${UtilsModule.escapeHtml(theme.status || 'N/A')})
                    </summary>
                    <h3>Resumen del Tema</h3>
                    ${summaryHtml}
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Índice</th>
                                    <th>Fecha</th>
                                    <th>Remitente</th>
                                    <th>Destinatario</th>
                                    <th>Asunto</th>
                                    <th>Descripción</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${theme.emails?.map(email => {
                                    console.log('Rendering theme email:', { index: email.index, message_id: email.message_id });
                                    const index = email.index && email.index !== 'N/A' ? email.index : email.message_id;
                                    return `
                                        <tr>
                                            <td><a href="#" class="theme-email-link" data-index="${UtilsModule.escapeHtml(index)}">${UtilsModule.truncateIndex(index)}</a></td>
                                            <td>${UtilsModule.escapeHtml(email.date ? new Date(email.date).toLocaleString() : 'N/A')}</td>
                                            <td>${UtilsModule.escapeHtml(email.from || 'N/A')}</td>
                                            <td>${UtilsModule.escapeHtml(email.to || 'N/A')}</td>
                                            <td>${UtilsModule.escapeHtml(email.subject || '')}</td>
                                            <td>${UtilsModule.escapeHtml(email.description?.slice(0, 100) || '')}${email.description?.length > 100 ? '...' : ''}</td>
                                        </tr>
                                    `;
                                }).join('') || ''}
                            </tbody>
                        </table>
                    </div>
                `;
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
                            if (!response.ok) {
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }
                            const email = await response.json();
                            console.log('Email details:', email);
                            const attachmentsContent = Array.isArray(email.attachments_content)
                                ? email.attachments_content.join('\n')
                                : email.attachments_content || '';
                            document.getElementById('email-details').innerHTML = `
                                <p><strong>Índice:</strong> ${UtilsModule.truncateIndex(email.index)}</p>
                                <p><strong>ID:</strong> ${UtilsModule.escapeHtml(email.message_id || 'N/A', true)}</p>
                                <p><strong>De:</strong> ${UtilsModule.escapeHtml(email.from || 'N/A')}</p>
                                <p><strong>Para:</strong> ${UtilsModule.escapeHtml(email.to || 'N/A')}</p>
                                <p><strong>Asunto:</strong> ${UtilsModule.escapeHtml(email.subject || '')}</p>
                                <p><strong>Fecha:</strong> ${UtilsModule.escapeHtml(email.date || '')}</p>
                                <p><strong>Resumen:</strong> ${UtilsModule.escapeHtml(email.summary || 'N/A')}</p>
                                <p><strong>Cuerpo:</strong> ${UtilsModule.escapeHtml(email.body || '')}</p>
                                <p><strong>Adjuntos:</strong> ${UtilsModule.escapeHtml(attachmentsContent)}</p>
                            `;
                            document.getElementById('email-modal').style.display = 'flex';
                            document.getElementById('not-relevant').dataset.id = email.message_id || email.index;
                        } catch (err) {
                            console.error('Error fetching email:', err);
                            alert('Error al cargar los detalles del correo: ' + err.message);
                        }
                    });
                });
            });

            // Ensure tab is shown after rendering
            if (container === this.themesList) {
                this.showTab();
            } else {
                ConversationsModule.showThemesTab();
            }
        } catch (error) {
            console.error('Error rendering themes:', error);
            container.innerHTML = '<p id="error-message">Error al renderizar temas: ' + UtilsModule.escapeHtml(error.message) + '</p>';
            if (container === this.themesList) {
                this.showTab();
            } else {
                ConversationsModule.showThemesTab();
            }
        }
    }
};