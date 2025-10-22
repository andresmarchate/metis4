/* Artifact ID: 6fa72aa8-c531-4216-9e6e-88c3dc8ddeda */
/* Version: g8h9i0j1-2345-6789-g0h1-i23456789012 */
const SearchModule = {
    init({ currentQuery, currentMinRelevance, currentPage, resultsPerPage, filterCounts, currentEmails, setCurrentEmails, setFilterCounts, setTotalPages }) {
        this.currentQuery = currentQuery;
        this.currentMinRelevance = currentMinRelevance;
        this.currentPage = currentPage;
        this.resultsPerPage = resultsPerPage;
        this.filterCounts = filterCounts || { remove: {}, add: {} };
        this.currentEmails = currentEmails || [];
        this.setCurrentEmails = setCurrentEmails;
        this.setExternalFilterCounts = setFilterCounts; // Store external setter
        this.setTotalPages = setTotalPages;

        // DOM elements
        this.form = document.getElementById('search-form');
        this.queryInput = document.getElementById('query');
        this.minRelevanceInput = document.getElementById('min-relevance');
        this.clearCacheInput = document.getElementById('clear-cache');
        this.resultsTable = document.getElementById('results-table');
        this.resultsBody = document.getElementById('results-body');
        this.resultsCount = document.getElementById('results-count');
        this.noResults = document.getElementById('no-results');
        this.pagination = document.getElementById('pagination');
        this.prevPageBtn = document.getElementById('prev-page');
        this.nextPageBtn = document.getElementById('next-page');
        this.pageNumbersSpan = document.getElementById('page-numbers');
        this.filterPrompt = document.getElementById('filter-prompt');
        this.applyFilterBtn = document.getElementById('apply-filter');
        this.resetFiltersBtn = document.getElementById('reset-filters');
        this.filtersList = document.getElementById('filters-list');
        this.errorMessage = document.getElementById('error-message');
        this.analyzeThemesBtn = document.getElementById('analyze-themes');
        this.searchSection = document.getElementById('search-section');

        // Debug DOM initialization
        console.log('SearchModule init: searchSection found:', !!this.searchSection);

        // Event listeners
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.currentPage = 1;
            console.log('Search form submitted');
            this.performSearch();
        });

        this.applyFilterBtn.addEventListener('click', () => {
            const filter = UtilsModule.parseFilterPrompt(this.filterPrompt.value);
            if (filter) {
                let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
                filters.push(filter);
                sessionStorage.setItem('filters', JSON.stringify(filters));
                this.filterPrompt.value = '';
                console.log('Applying filter:', filter);
                this.performSearch();
            } else {
                alert('Formato de filtro inválido. Usa "elimina correos que incluyan término1, término2" o "añade correos que incluyan término1, término2".');
            }
        });

        this.resetFiltersBtn.addEventListener('click', () => {
            sessionStorage.setItem('filters', JSON.stringify([]));
            this.filterPrompt.value = '';
            console.log('Resetting filters');
            this.performSearch();
        });

        this.prevPageBtn.addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                console.log('Navigating to previous page:', this.currentPage);
                this.performSearch();
            }
        });

        this.nextPageBtn.addEventListener('click', () => {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
                console.log('Navigating to next page:', this.currentPage);
                this.performSearch();
            }
        });

        this.analyzeThemesBtn.addEventListener('click', async () => {
            console.log('Analyze themes button clicked', { currentEmails: this.currentEmails });
            if (!this.currentEmails || !Array.isArray(this.currentEmails) || this.currentEmails.length === 0) {
                console.warn('No valid emails to analyze', { currentEmails: this.currentEmails });
                this.errorMessage.textContent = 'No hay correos válidos para analizar temas.';
                this.errorMessage.style.display = 'block';
                return;
            }
            const emailIds = await this.fetchAllSearchResults();
            console.log('Fetched email IDs for theme analysis:', emailIds);
            if (!emailIds || !Array.isArray(emailIds) || emailIds.length === 0) {
                console.warn('No valid email identifiers for theme analysis', { emailIds });
                this.errorMessage.textContent = 'No hay identificadores de correos válidos para analizar.';
                this.errorMessage.style.display = 'block';
                return;
            }
            try {
                console.log('Sending theme analysis request for emails:', emailIds);
                const response = await fetch('/api/analyze_themes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email_ids: emailIds.map(email => email.index || email.message_id).filter(id => id && id !== 'N/A') })
                });
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ error: `HTTP error: ${response.status}` }));
                    throw new Error(errorData.error || `HTTP error: ${response.status}`);
                }
                const data = await response.json();
                console.log('Theme analysis response:', data);
                if (data.error) {
                    throw new Error(data.error);
                }
                ThemesModule.renderThemes(data.themes || []);
            } catch (error) {
                console.error('Error analyzing themes:', error.message);
                this.errorMessage.textContent = `Error al analizar temas: ${error.message}`;
                this.errorMessage.style.display = 'block';
                ThemesModule.setCurrentThemes([]);
            }
        });
    },

    // Internal method to update filterCounts
    setFilterCounts(counts) {
        console.log('Setting filterCounts:', JSON.stringify(counts, null, 2));
        this.filterCounts = counts || { remove: {}, add: {} };
        // Update external state if setter exists
        if (this.setExternalFilterCounts) {
            this.setExternalFilterCounts(this.filterCounts);
        }
        console.log('Updated filterCounts:', JSON.stringify(this.filterCounts, null, 2));
    },

    showTab() {
        if (!this.searchSection) {
            console.error('searchSection is undefined, cannot show tab');
            return;
        }
        console.log('Showing Consultas tab');
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(tabLink => tabLink.classList.remove('active'));
        this.searchSection.classList.add('active');
        const tabLink = document.querySelector('.tab-link[data-tab="consultas"]');
        if (tabLink) {
            tabLink.classList.add('active');
        } else {
            console.warn('Tab link for "consultas" not found');
        }
    },

    async fetchAllSearchResults() {
        let allEmails = [];
        let page = 1;
        let totalResults = 0;
        const filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        do {
            try {
                console.log(`Fetching search results for page ${page}`);
                const response = await fetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: this.currentQuery,
                        minRelevance: this.currentMinRelevance,
                        page,
                        resultsPerPage: this.resultsPerPage,
                        clearCache: this.clearCacheInput.checked,
                        filters
                    })
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                console.log(`Search response for page ${page}:`, data);
                if (!Array.isArray(data.results)) {
                    console.warn('No results returned for page:', page);
                    break;
                }
                allEmails.push(...data.results.map(result => ({
                    message_id: result.message_id,
                    index: result.index
                })));
                totalResults = data.totalResults || 0;
                page++;
            } catch (err) {
                console.error(`Error fetching page ${page}:`, err);
                break;
            }
        } while (allEmails.length < totalResults);
        console.log('All emails retrieved:', allEmails);
        return allEmails.filter(email => email.index || email.message_id);
    },

    async performSearch() {
        console.log('Starting performSearch');
        const query = this.queryInput.value.trim();
        const minRelevance = parseInt(this.minRelevanceInput.value) || 10;
        const clearCache = this.clearCacheInput.checked;
        let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        this.currentQuery = query;
        this.currentMinRelevance = Math.max(0, Math.min(minRelevance, 100));

        if (!query) {
            console.warn('Empty query submitted');
            this.errorMessage.textContent = 'Por favor, introduce una consulta.';
            this.errorMessage.style.display = 'block';
            return;
        }

        this.errorMessage.style.display = 'none';

        if (!sessionStorage.getItem('originalQuery')) {
            sessionStorage.setItem('originalQuery', query);
        } else if (clearCache && query !== sessionStorage.getItem('originalQuery')) {
            sessionStorage.setItem('originalQuery', query);
            sessionStorage.setItem('filters', JSON.stringify([]));
            filters = [];
            this.renderFilters(filters, this.filterCounts);
        }

        try {
            this.resultsBody.innerHTML = '';
            this.resultsTable.style.display = 'none';
            this.noResults.style.display = 'none';
            this.resultsCount.style.display = 'none';
            this.analyzeThemesBtn.style.display = 'none';
            this.showTab();

            console.log('Sending POST request to /api/search', { query, minRelevance: this.currentMinRelevance, page: this.currentPage, clearCache, filters });
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    minRelevance: this.currentMinRelevance,
                    page: this.currentPage,
                    resultsPerPage: this.resultsPerPage,
                    clearCache,
                    filters
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Search response:', data);
            console.log('Filter counts received:', JSON.stringify(data.filter_counts, null, 2));

            const results = data.results || [];
            const totalResults = data.totalResults || 0;
            this.setFilterCounts(data.filter_counts || { remove: {}, add: {} });
            console.log('Updated filterCounts:', JSON.stringify(this.filterCounts, null, 2));
            const newEmails = results.map(result => ({
                message_id: result.message_id,
                index: result.index
            })).filter(email => email.index || email.message_id);
            this.currentEmails = newEmails;
            this.setCurrentEmails(newEmails);
            console.log('Updated currentEmails:', this.currentEmails);

            if (!Array.isArray(results) || results.length === 0) {
                console.log('No results returned');
                this.noResults.style.display = 'block';
                this.updatePagination(0);
                this.renderFilters(filters, this.filterCounts);
                return;
            }

            this.resultsCount.textContent = `Se encontraron ${totalResults} correos relevantes`;
            this.resultsCount.style.display = 'block';
            this.analyzeThemesBtn.style.display = 'block';

            this.resultsTable.style.display = 'table';
            results.forEach(result => {
                console.log('Rendering search result:', { index: result.index, message_id: result.message_id });
                if (!result.message_id && !result.index) {
                    console.warn('Missing message_id and index in result:', result);
                }
                const index = result.index && result.index !== 'N/A' ? result.index : result.message_id;
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><a href="#" class="index-link" data-index="${UtilsModule.escapeHtml(index)}">${UtilsModule.truncateIndex(index)}</a></td>
                    <td>${UtilsModule.escapeHtml(result.date || '')}</td>
                    <td>${UtilsModule.escapeHtml(result.from || 'N/A')}</td>
                    <td>${UtilsModule.escapeHtml(result.to || 'N/A')}</td>
                    <td>${UtilsModule.escapeHtml(result.subject || '')}</td>
                    <td>${UtilsModule.escapeHtml((result.description || '').slice(0, 100))}${result.description && result.description.length > 100 ? '...' : ''}</td>
                    <td>${UtilsModule.escapeHtml((result.relevant_terms || []).join(', '))}</td>
                    <td>${result.relevance || ''}</td>
                    <td>${UtilsModule.escapeHtml(result.explanation || '')}</td>
                    <td><button class="not-relevant" data-id="${UtilsModule.escapeHtml(result.message_id || result.index || 'N/A')}">No Relevante</button></td>
                `;
                this.resultsBody.appendChild(row);
            });

            this.updatePagination(totalResults);
            this.renderFilters(filters, this.filterCounts);

            this.resultsBody.querySelectorAll('.index-link').forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = e.target.dataset.index;
                    console.log('Clicked index link with identifier:', identifier);
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

            this.resultsBody.querySelectorAll('.not-relevant').forEach(button => {
                button.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = button.dataset.id;
                    console.log('Clicked not-relevant button with identifier:', identifier);
                    if (!identifier || identifier === 'N/A') {
                        console.error('No valid identifier found for button:', button);
                        alert('Identificador de correo no válido.');
                        return;
                    }
                    try {
                        console.log('Sending feedback for identifier:', identifier);
                        const response = await fetch('/api/feedback', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                query: this.currentQuery,
                                message_id: identifier,
                                is_relevant: false
                            })
                        });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        console.log('Feedback sent successfully');
                        alert('Retroalimentación enviada.');
                    } catch (err) {
                        console.error('Error sending feedback:', err);
                        alert('Error al enviar retroalimentación: ' + err.message);
                    }
                });
            });
        } catch (err) {
            console.error('Error during search:', err);
            this.errorMessage.textContent = 'Error al realizar la búsqueda: ' + err.message;
            this.errorMessage.style.display = 'block';
            this.updatePagination(0);
            this.renderFilters(filters, this.filterCounts);
        }
    },

    updatePagination(totalResults) {
        this.setTotalPages(Math.ceil(totalResults / this.resultsPerPage));
        console.log('Total results:', totalResults, 'Total pages:', this.totalPages || 1);

        this.prevPageBtn.disabled = this.currentPage === 1;
        this.nextPageBtn.disabled = this.currentPage === (this.totalPages || 1) || (this.totalPages || 1) === 0;

        let pageNumbers = '';
        const maxPagesToShow = 10;
        let startPage = Math.max(1, this.currentPage - Math.floor(maxPagesToShow / 2));
        let endPage = Math.min(this.totalPages || 1, startPage + maxPagesToShow - 1);

        if (endPage - startPage + 1 < maxPagesToShow) {
            startPage = Math.max(1, endPage - maxPagesToShow + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            if (i === this.currentPage) {
                pageNumbers += `<span class="current-page">${i}</span>`;
            } else {
                pageNumbers += `<a href="#" class="page-link" data-page="${i}">${i}</a>`;
            }
        }
        this.pageNumbersSpan.innerHTML = pageNumbers;

        this.pageNumbersSpan.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.currentPage = parseInt(e.target.dataset.page);
                console.log('Navigating to page via link:', this.currentPage);
                this.performSearch();
            });
        });

        this.pagination.style.display = totalResults > 0 ? 'flex' : 'none';
    },

    renderFilters(filters, counts) {
        console.log('Rendering filters:', filters, 'with counts:', JSON.stringify(counts, null, 2));
        this.filtersList.innerHTML = '';
        if (!Array.isArray(filters) || filters.length === 0) {
            console.log('No filters to render');
            return;
        }
        filters.forEach((filter, index) => {
            console.log('Creating filter item:', { filter, index });
            const li = document.createElement('li');
            const actionText = filter.action === 'remove' ? 'Eliminar' : 'Añadir';
            const termsText = UtilsModule.escapeHtml(filter.terms.join(', '));
            const termsKey = filter.terms.join(',').toLowerCase(); // Match backend normalization
            console.log('Filter termsKey:', termsKey);
            const count = filter.action === 'remove' ? (counts.remove[termsKey] || 0) : (counts.add[termsKey] || 0);
            console.log('Filter count for', termsText, ':', count);
            const countText = filter.action === 'remove' 
                ? `(<a href="#" class="filter-count-link" data-index="${index}">${count} correo${count !== 1 ? 's' : ''} eliminado${count !== 1 ? 's' : ''}</a>)`
                : `(<a href="#" class="filter-count-link" data-index="${index}">${count} correo${count !== 1 ? 's' : ''} añadido${count !== 1 ? 's' : ''}</a>)`;
            li.innerHTML = `${actionText}: ${termsText} ${countText}`;

            const removeBtn = document.createElement('button');
            removeBtn.textContent = 'X';
            removeBtn.className = 'remove-filter';
            removeBtn.onclick = () => this.removeFilter(index);
            li.appendChild(removeBtn);

            const notRelevantBtn = document.createElement('button');
            notRelevantBtn.textContent = 'Marcar como No Relevantes';
            notRelevantBtn.className = 'not-relevant-filter';
            notRelevantBtn.onclick = () => this.markFilterAsNotRelevant(filter, index);
            li.appendChild(notRelevantBtn);

            this.filtersList.appendChild(li);

            li.querySelector('.filter-count-link').addEventListener('click', (e) => {
                e.preventDefault();
                console.log('Filter count link clicked:', { filter, index });
                this.showFilterEmailsModal(filter);
            });
        });
    },

    removeFilter(index) {
        console.log('Removing filter at index:', index);
        let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        filters.splice(index, 1);
        sessionStorage.setItem('filters', JSON.stringify(filters));
        this.renderFilters(filters, this.filterCounts);
        this.performSearch();
    },

    async markFilterAsNotRelevant(filter, index) {
        console.log('Marking emails for filter as not relevant:', filter);
        try {
            const response = await fetch('/api/bulk_feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: this.currentQuery,
                    filter: {
                        action: filter.action,
                        terms: filter.terms
                    }
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('Bulk feedback response:', result);
            alert(`Se marcaron ${result.affected_count} correos como no relevantes.`);
            this.performSearch();
        } catch (err) {
            console.error('Error sending bulk feedback:', err);
            alert('Error al marcar correos como no relevantes: ' + err.message);
        }
    },

    async showFilterEmailsModal(filter) {
        console.log('Fetching emails for filter:', filter);
        try {
            const response = await fetch('/api/filter_emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: this.currentQuery,
                    filter: filter,
                    page: 1,
                    results_per_page: 25
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Filter emails response:', data);
            console.log('Emails in filter modal:', data.results.map(email => ({
                message_id: email.message_id,
                index: email.index,
                subject: email.subject,
                relevant_terms: email.relevant_terms || [],
                description: email.description,
                explanation: email.explanation
            })));

            const filterModal = document.createElement('div');
            filterModal.className = 'modal';
            filterModal.style.display = 'flex';
            filterModal.innerHTML = `
                <div class="modal-content">
                    <span class="close">×</span>
                    <h2>Correos ${filter.action === 'remove' ? 'Eliminados' : 'Añadidos'} por el Filtro: ${UtilsModule.escapeHtml(filter.terms.join(', '))}</h2>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Índice</th>
                                    <th>Fecha</th>
                                    <th>Asunto</th>
                                    <th>Remitente</th>
                                    <th>Destinatario</th>
                                    <th>Descripción</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.results.map(email => `
                                    <tr>
                                        <td><a href="#" class="index-link" data-index="${UtilsModule.escapeHtml(email.index)}">${UtilsModule.truncateIndex(email.index)}</a></td>
                                        <td>${UtilsModule.escapeHtml(new Date(email.date).toLocaleString())}</td>
                                        <td>${UtilsModule.escapeHtml(email.subject)}</td>
                                        <td>${UtilsModule.escapeHtml(email.from)}</td>
                                        <td>${UtilsModule.escapeHtml(email.to)}</td>
                                        <td>${UtilsModule.escapeHtml(email.description)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
            document.body.appendChild(filterModal);

            filterModal.querySelector('.close').addEventListener('click', () => {
                console.log('Closing filter modal');
                filterModal.remove();
            });
            filterModal.addEventListener('click', (e) => {
                if (e.target === filterModal) {
                    console.log('Closing filter modal via background click');
                    filterModal.remove();
                }
            });

            filterModal.querySelectorAll('.index-link').forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const identifier = e.target.dataset.index;
                    console.log('Clicked filter modal index link with identifier:', identifier);
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
        } catch (error) {
            console.error('Error fetching filter emails:', error);
            alert('Error al cargar los correos del filtro: ' + error.message);
        }
    }
};