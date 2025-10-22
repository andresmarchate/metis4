// main.js
document.addEventListener('DOMContentLoaded', () => {
    console.log('main.js loaded successfully');

    // Select DOM elements
    const form = document.getElementById('search-form');
    const queryInput = document.getElementById('query');
    const minRelevanceInput = document.getElementById('min-relevance');
    const clearCacheInput = document.getElementById('clear-cache');
    const resultsTable = document.getElementById('results-table');
    const resultsBody = document.getElementById('results-body');
    const resultsCount = document.getElementById('results-count');
    const noResults = document.getElementById('no-results');
    const pagination = document.getElementById('pagination');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const pageNumbersSpan = document.getElementById('page-numbers');
    const modal = document.getElementById('email-modal');
    const modalContent = document.getElementById('email-details');
    const closeModal = document.querySelector('.close');
    const notRelevantBtn = document.getElementById('not-relevant');
    const filterPrompt = document.getElementById('filter-prompt');
    const applyFilterBtn = document.getElementById('apply-filter');
    const resetFiltersBtn = document.getElementById('reset-filters');
    const filtersList = document.getElementById('filters-list');
    const errorMessage = document.getElementById('error-message');

    let currentQuery = '';
    let currentMinRelevance = 10;
    let currentPage = 1;
    let totalPages = 1;
    const resultsPerPage = 25;

    if (!form) {
        console.error('Search form not found in DOM');
        return;
    }

    // Normalizar texto eliminando diacríticos y convirtiendo a minúsculas
    function normalizeText(text) {
        if (!text || typeof text !== 'string') return text;
        return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    }

    // Escape HTML characters to prevent XSS
    function escapeHtml(unsafe, isMessageId = false) {
        if (!unsafe) return 'N/A';
        let safe = typeof unsafe === 'string' ? unsafe : String(unsafe);
        console.log('Escaping HTML:', { unsafe, isMessageId });

        if (isMessageId || safe.match(/<[^>]+@[^>]+>/)) {
            console.log('Preserving email format:', safe);
            return safe;
        }

        console.log('Escaping non-email text:', safe);
        return safe
            .replace(/&/g, "&")
            .replace(/</g, "<")
            .replace(/>/g, ">")
            .replace(/"/g, "")
            .replace(/'/g, "'");
    }

    // Parsear prompt para extraer acción y términos
    function parseFilterPrompt(prompt) {
        if (!prompt || typeof prompt !== 'string') return null;
        const normalizedPrompt = normalizeText(prompt.trim());
        const removeMatch = normalizedPrompt.match(/^(elimina|excluye|remove|delete)\s+correos\s+que\s+incluyan\s+(.+)/i);
        const addMatch = normalizedPrompt.match(/^(anade|añade|agrega|incluye|add|include)\s+correos\s+que\s+incluyan\s+(.+)/i);

        if (removeMatch) {
            const terms = removeMatch[2].split(',').map(term => term.trim()).filter(term => term);
            return { action: 'remove', terms };
        } else if (addMatch) {
            const terms = addMatch[2].split(',').map(term => term.trim()).filter(term => term);
            return { action: 'add', terms };
        }
        return null;
    }

    // Renderizar lista de filtros
    function renderFilters(filters) {
        filtersList.innerHTML = '';
        filters.forEach((filter, index) => {
            const li = document.createElement('li');
            const actionText = filter.action === 'remove' ? 'Eliminar' : 'Añadir';
            li.innerHTML = `${actionText}: ${escapeHtml(filter.terms.join(', '))}`;
            const removeBtn = document.createElement('button');
            removeBtn.textContent = 'X';
            removeBtn.onclick = () => removeFilter(index);
            li.appendChild(removeBtn);
            filtersList.appendChild(li);
        });
    }

    // Eliminar un filtro y recargar resultados
    function removeFilter(index) {
        let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        filters.splice(index, 1);
        sessionStorage.setItem('filters', JSON.stringify(filters));
        renderFilters(filters);
        performSearch();
    }

    // Update pagination controls
    function updatePagination(totalResults) {
        totalPages = Math.ceil(totalResults / resultsPerPage);
        console.log('Total results:', totalResults, 'Total pages:', totalPages);

        prevPageBtn.disabled = currentPage === 1;
        nextPageBtn.disabled = currentPage === totalPages || totalPages === 0;

        let pageNumbers = '';
        const maxPagesToShow = 10;
        let startPage = Math.max(1, currentPage - Math.floor(maxPagesToShow / 2));
        let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);

        if (endPage - startPage + 1 < maxPagesToShow) {
            startPage = Math.max(1, endPage - maxPagesToShow + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            if (i === currentPage) {
                pageNumbers += `<span class="current-page">${i}</span>`;
            } else {
                pageNumbers += `<a href="#" class="page-link" data-page="${i}">${i}</a>`;
            }
        }
        pageNumbersSpan.innerHTML = pageNumbers;

        document.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                currentPage = parseInt(e.target.dataset.page);
                performSearch();
            });
        });

        pagination.style.display = totalResults > 0 ? 'block' : 'none';
    }

    // Perform search with pagination and filters
    async function performSearch() {
        const query = queryInput.value.trim();
        const minRelevance = parseInt(minRelevanceInput.value) || 10;
        const clearCache = clearCacheInput.checked;
        const filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
        currentQuery = query;
        currentMinRelevance = Math.max(0, Math.min(minRelevance, 100));

        if (!query) {
            console.warn('Empty query submitted');
            errorMessage.textContent = 'Por favor, introduce una consulta.';
            errorMessage.style.display = 'block';
            return;
        }

        errorMessage.style.display = 'none';

        // Guardar consulta original si es nueva
        if (!sessionStorage.getItem('originalQuery') || clearCache) {
            sessionStorage.setItem('originalQuery', query);
            sessionStorage.setItem('filters', JSON.stringify([]));
            renderFilters([]);
        }

        try {
            resultsBody.innerHTML = '';
            resultsTable.style.display = 'none';
            noResults.style.display = 'none';
            resultsCount.style.display = 'none';

            console.log('Sending POST request to /api/search', { query, minRelevance: currentMinRelevance, page: currentPage, clearCache, filters });
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    minRelevance: currentMinRelevance,
                    page: currentPage,
                    resultsPerPage,
                    clearCache,
                    filters
                })
            });

            console.log('Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Search response:', data);

            const results = data.results || [];
            const totalResults = data.totalResults || 0;

            if (!Array.isArray(results) || results.length === 0) {
                console.log('No results returned');
                noResults.style.display = 'block';
                updatePagination(0);
                return;
            }

            resultsCount.textContent = `Se han encontrado ${totalResults} correos relevantes`;
            resultsCount.style.display = 'block';

            resultsTable.style.display = 'table';
            results.forEach(result => {
                console.log('Processing result:', { from: result.from, to: result.to });
                if (!result.message_id) {
                    console.warn('Missing message_id in result:', result);
                }
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><a href="#" class="index-link" data-id="${escapeHtml(result.message_id || '', true)}">${result.index || ''}</a></td>
                    <td>${escapeHtml(result.date || '')}</td>
                    <td>${result.from || 'N/A'}</td>
                    <td>${result.to || 'N/A'}</td>
                    <td>${escapeHtml(result.subject || '')}</td>
                    <td>${escapeHtml((result.description || '').slice(0, 100))}${result.description && result.description.length > 100 ? '...' : ''}</td>
                    <td>${escapeHtml((result.relevant_terms || []).join(', '))}</td>
                    <td>${result.relevance || ''}</td>
                    <td>${escapeHtml(result.explanation || '')}</td>
                    <td><button class="not-relevant" data-id="${escapeHtml(result.message_id || '', true)}">No Relevante</button></td>
                `;
                resultsBody.appendChild(row);
            });

            updatePagination(totalResults);

            const indexLinks = document.querySelectorAll('.index-link');
            console.log('Found index links:', indexLinks.length);
            indexLinks.forEach(link => {
                link.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const messageId = e.target.dataset.id;
                    console.log('Clicked index link with message_id:', messageId);
                    if (!messageId) {
                        console.error('No message_id found for link:', e.target);
                        alert('ID de correo no válido.');
                        return;
                    }
                    try {
                        console.log('Fetching email details for:', messageId);
                        const response = await fetch(`/api/email/${encodeURIComponent(messageId)}`);
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        const email = await response.json();
                        console.log('Email details:', email);
                        console.log('Rendering message_id:', email.message_id);
                        console.log('Rendering from:', email.from);
                        console.log('Rendering to:', email.to);
                        const attachmentsContent = Array.isArray(email.attachments_content)
                            ? email.attachments_content.join('\n')
                            : email.attachments_content || 'N/A';
                        modalContent.innerHTML = `
                            <p><strong>ID:</strong> ${escapeHtml(email.message_id || 'N/A', true)}</p>
                            <p><strong>De:</strong> ${email.from || 'N/A'}</p>
                            <p><strong>Para:</strong> ${email.to || 'N/A'}</p>
                            <p><strong>Asunto:</strong> ${escapeHtml(email.subject || 'N/A')}</p>
                            <p><strong>Fecha:</strong> ${escapeHtml(email.date || 'N/A')}</p>
                            <p><strong>Resumen:</strong> ${escapeHtml(email.summary || 'N/A')}</p>
                            <p><strong>Cuerpo:</strong> ${escapeHtml(email.body || 'N/A')}</p>
                            <p><strong>Adjuntos:</strong> ${escapeHtml(attachmentsContent)}</p>
                        `;
                        modal.style.display = 'block';
                        notRelevantBtn.dataset.id = messageId;
                    } catch (error) {
                        console.error('Error fetching email:', error);
                        alert('Error al cargar los detalles del correo: ' + error.message);
                    }
                });
            });

            document.querySelectorAll('.not-relevant').forEach(button => {
                button.addEventListener('click', async () => {
                    const messageId = button.dataset.id;
                    console.log('Marking email as not relevant (table):', messageId);
                    if (!messageId) {
                        console.error('No message_id for feedback button');
                        alert('ID de correo no válido.');
                        return;
                    }
                    try {
                        const response = await fetch('/api/feedback', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                query: currentQuery,
                                message_id: messageId,
                                is_relevant: false
                            })
                        });
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        console.log('Feedback sent successfully');
                        alert('Retroalimentación enviada.');
                    } catch (error) {
                        console.error('Error sending feedback:', error);
                        alert('Error al enviar retroalimentación: ' + error.message);
                    }
                });
            });
        } catch (error) {
            console.error('Error during search:', error);
            errorMessage.textContent = 'Error al realizar la búsqueda: ' + error.message;
            errorMessage.style.display = 'block';
            updatePagination(0);
        }
    }

    prevPageBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            performSearch();
        }
    });

    nextPageBtn.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            performSearch();
        }
    });

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        currentPage = 1;
        performSearch();
    });

    if (applyFilterBtn) {
        applyFilterBtn.addEventListener('click', () => {
            const prompt = filterPrompt.value.trim();
            const filter = parseFilterPrompt(prompt);
            if (!filter || filter.terms.length === 0) {
                errorMessage.textContent = 'Prompt inválido. Ejemplo: "elimina correos que incluyan reunión, proyecto" o "añade correos que incluyan viaje, reserva"';
                errorMessage.style.display = 'block';
                return;
            }
            errorMessage.style.display = 'none';
            let filters = JSON.parse(sessionStorage.getItem('filters') || '[]');
            filters.push(filter);
            sessionStorage.setItem('filters', JSON.stringify(filters));
            renderFilters(filters);
            filterPrompt.value = '';
            performSearch();
        });
    }

    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', () => {
            sessionStorage.setItem('filters', JSON.stringify([]));
            renderFilters([]);
            performSearch();
        });
    }

    if (closeModal) {
        closeModal.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });

    if (notRelevantBtn) {
        notRelevantBtn.addEventListener('click', async () => {
            const messageId = notRelevantBtn.dataset.id;
            console.log('Marking email as not relevant from modal:', messageId);
            if (!messageId) {
                console.error('No message_id for modal feedback');
                alert('ID de correo no válido.');
                return;
            }
            try {
                const response = await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: currentQuery,
                        message_id: messageId,
                        is_relevant: false
                    })
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                console.log('Feedback sent successfully');
                alert('Retroalimentación enviada.');
                modal.style.display = 'none';
            } catch (error) {
                console.error('Error sending feedback:', error);
                alert('Error al enviar retroalimentación: ' + error.message);
            }
        });
    }

    // Cargar filtros existentes
    renderFilters(JSON.parse(sessionStorage.getItem('filters') || '[]'));
});