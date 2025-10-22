const AgattaModule = {
    // Pagination variables for TODOs
    currentPage: 1,
    pageSize: 10,
    totalTodos: 0,

    init() {
        console.log('AgattaModule initializing');
        this.agattaSection = document.getElementById('agatta-section');
        this.agattaContent = document.getElementById('agatta-content');
        this.todosList = document.getElementById('todos-list');
        if (!this.agattaSection) {
            console.error('Agatta section element not found (#agatta-section)');
        }
        if (!this.agattaContent) {
            console.error('Agatta content element not found (#agatta-content)');
        }
        if (!this.todosList) {
            console.error('Todos list element not found (#todos-list)');
        } else {
            console.log('Todos list element found:', this.todosList);
        }
    },

    showTab() {
        console.log('Showing AGATTA tab');
        if (!this.agattaSection || !this.agattaContent) {
            console.error('Cannot show AGATTA tab: elements not initialized');
            return;
        }
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-link').forEach(link => link.classList.remove('active'));
        this.agattaSection.classList.add('active');
        const tabLink = document.querySelector('.tab-link[data-tab="agatta"]');
        if (tabLink) {
            tabLink.classList.add('active');
        } else {
            console.warn('AGATTA tab link not found');
        }
        this.loadStats();
        this.loadTodos(); // Cargar TODOs al mostrar la pestaña
    },

    async loadStats() {
        console.log('Loading AGATTA stats');
        try {
            this.showLoading();
            const response = await fetch('/api/agatta/stats', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            console.log('Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const stats = await response.json();
            console.log('Stats received:', stats);
            this.renderStats(stats);
        } catch (error) {
            console.error('Error loading AGATTA stats:', error.message);
            if (this.agattaContent) {
                this.agattaContent.innerHTML = `<p>Error al cargar estadísticas: ${error.message}</p>`;
            }
        } finally {
            this.hideLoading();
        }
    },

    renderStats(stats) {
        if (!this.agattaContent) {
            console.error('Cannot render stats: agattaContent is null');
            return;
        }
        console.log('Rendering stats:', stats);
        this.agattaContent.innerHTML = `
            <h2>Estadísticas de AGATTA</h2>
            <div class="todo-group">
                <h3>Total TODOs: ${stats.total_todos}</h3>
                <button class="load-todos" data-type="total">Cargar Listado</button>
                <div class="todos-list" id="total-todos-list"></div>
            </div>
            <div class="todo-group">
                <h3>Completados: ${stats.completed}</h3>
                <button class="load-todos" data-type="completed">Cargar Listado</button>
                <div class="todos-list" id="completed-todos-list"></div>
            </div>
        `;

        document.querySelectorAll('.load-todos').forEach(button => {
            button.addEventListener('click', () => {
                const type = button.getAttribute('data-type');
                if (type === 'total') {
                    this.loadTotalTodos();
                } else if (type === 'completed') {
                    this.loadCompletedTodos();
                }
            });
        });
    },

    async loadTotalTodos() {
        try {
            this.showLoading();
            const response = await fetch('/api/agatta/todos?completed=all', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            this.renderTodos(data.todos, 'total-todos-list');
        } catch (error) {
            console.error('Error loading total todos:', error);
            document.getElementById('total-todos-list').innerHTML = `<p>Error al cargar TODOs: ${error.message}</p>`;
        } finally {
            this.hideLoading();
        }
    },

    async loadCompletedTodos() {
        try {
            this.showLoading();
            const response = await fetch('/api/agatta/todos?completed=true', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            this.renderTodos(data.todos, 'completed-todos-list');
        } catch (error) {
            console.error('Error loading completed todos:', error);
            document.getElementById('completed-todos-list').innerHTML = `<p>Error al cargar TODOs completados: ${error.message}</p>`;
        } finally {
            this.hideLoading();
        }
    },

    renderTodos(todos, containerId) {
        const container = document.getElementById(containerId);
        container.innerHTML = '';
        if (todos.length === 0) {
            container.innerHTML = '<p>No hay TODOs en esta categoría.</p>';
            return;
        }
        const ul = document.createElement('ul');
        ul.className = 'todos-list';
        todos.forEach(todo => {
            const li = document.createElement('li');
            li.textContent = `${todo.subject} - ${todo.date} - From: ${todo.from}`;
            ul.appendChild(li);
        });
        container.appendChild(ul);
    },

    showLoading() {
        const loading = document.getElementById('loading');
        if (loading) {
            loading.style.display = 'flex';
            document.body.style.pointerEvents = 'none'; // Bloquear interacción
        }
    },

    hideLoading() {
        const loading = document.getElementById('loading');
        if (loading) {
            loading.style.display = 'none';
            document.body.style.pointerEvents = 'auto'; // Restaurar interacción
        }
    },

    // TODOs functionality moved from DashboardModule
    async loadTodos() {
        console.log('Iniciando carga de todos...');
        if (!this.todosList) {
            console.error('Cannot load todos: todosList is null');
            return;
        }
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const response = await fetch(`/api/agatta/todos?page=${this.currentPage}&page_size=${this.pageSize}&completed=false`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            console.log('Respuesta de todos recibida:', response.status);
            if (response.status === 401) {
                alert('Sesión expirada. Por favor, inicia sesión nuevamente.');
                window.location.href = '/login';
                return;
            }
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('Todos recibidos:', data.todos);
            this.totalTodos = data.total;
            this.renderTodosList(data.todos, data.total);
            console.log('Todos renderizados');
        } catch (error) {
            console.error('Error cargando todos:', error.message);
            this.todosList.innerHTML = `<p>Error al cargar TODOs: ${error.message}</p>`;
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    renderTodosList(todos, total) {
        if (!this.todosList) {
            console.error('Cannot render todos: todosList is null');
            return;
        }
        const totalPages = Math.ceil(total / this.pageSize);
        const now = new Date();
        this.todosList.innerHTML = `
            <img src="/static/images/agatta.jpg" alt="AGATTA Icon" style="max-width: 200px; max-height: 150px; margin-bottom: 10px;">
            <h2>TODOs de AGATTA</h2>
            <div class="todos-container">
                ${todos.map(todo => {
                    const todoDate = new Date(todo.date);
                    const diffTime = now - todoDate;
                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                    let colorClass;
                    if (diffDays <= 7) {
                        colorClass = 'todo-recent';
                    } else if (diffDays <= 14) {
                        colorClass = 'todo-medium';
                    } else {
                        colorClass = 'todo-old';
                    }
                    return `
                        <div class="todo-item ${colorClass}">
                            <input type="checkbox" ${todo.completed ? 'checked' : ''} onchange="AgattaModule.markCompleted('${todo._id}')">
                            <span class="todo-subject" onclick="AgattaModule.showThreadEmailsModal('${todo._id}')"><strong>Asunto:</strong> ${todo.subject || 'Sin Asunto'}</span>
                            <span><strong>Fecha de recepción:</strong> ${todoDate.toLocaleString('es-ES') || 'N/A'}</span>
                            <span><strong>Remitente:</strong> ${todo.from || 'N/A'}</span>
                            <span><strong>Resumen del hilo:</strong> ${todo.thread_summary || 'No disponible'}</span>
                            <span><strong>Acción propuesta:</strong> ${todo.proposed_action || 'No disponible'}</span>
                            <button onclick="AgattaModule.createDraft('${todo._id}')">Crear Borrador</button>
                        </div>
                    `;
                }).join('')}
            </div>
            <div class="pagination">
                <button onclick="AgattaModule.previousPage()" ${this.currentPage === 1 ? 'disabled' : ''}>Anterior</button>
                <span>Página ${this.currentPage} de ${totalPages}</span>
                <button onclick="AgattaModule.nextPage()" ${this.currentPage === totalPages ? 'disabled' : ''}>Siguiente</button>
            </div>
        `;
    },

    async showThreadEmailsModal(todoId) {
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const { emails, requestId } = await this.fetchThreadEmails(todoId);
            this.showEmailModal(emails, `Correos del Hilo`, requestId);
        } catch (error) {
            console.error('Error fetching thread emails:', error.message);
            alert('Error al cargar correos del hilo');
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    async fetchThreadEmails(todoId) {
        const requestId = Date.now();
        try {
            const response = await fetch('/api/thread_emails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ todo_id: todoId })
            });

            if (response.status === 401) {
                alert('Sesión expirada. Por favor, inicia sesión nuevamente.');
                window.location.href = '/login';
                return { emails: [], requestId };
            }

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }

            console.log(`Thread emails response [${requestId}]:`, data.emails);
            return { emails: data.emails, requestId };
        } catch (error) {
            console.error(`Error fetching thread emails [${requestId}]:`, error.message);
            return { emails: [], requestId };
        }
    },

    async markCompleted(taskId) {
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const response = await fetch('/api/agatta/complete_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            alert('Tarea marcada como completada exitosamente');
            this.loadTodos();
        } catch (error) {
            console.error('Error marking task as completed:', error.message);
            alert('Error al marcar la tarea como completada');
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    async createDraft(taskId) {
        const loadingElement = document.getElementById('loading');
        if (loadingElement) loadingElement.style.display = 'flex';
        try {
            const response = await fetch('/api/agatta/create_draft', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId })
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.success) {
                alert('Borrador creado exitosamente');
            } else {
                alert(`Error al crear borrador: ${data.error}`);
            }
        } catch (error) {
            console.error('Error creating draft:', error.message);
            alert('Error al crear el borrador');
        } finally {
            if (loadingElement) loadingElement.style.display = 'none';
        }
    },

    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.loadTodos();
        }
    },

    nextPage() {
        const totalPages = Math.ceil(this.totalTodos / this.pageSize);
        if (this.currentPage < totalPages) {
            this.currentPage++;
            this.loadTodos();
        }
    },

    showEmailModal(emails, title, requestId) {
        // Similar a DashboardModule.showEmailModal, adaptado para AgattaModule
        const modal = document.createElement('div');
        modal.className = 'modal';
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';

        const close = document.createElement('span');
        close.className = 'close';
        close.textContent = '×';
        modalContent.appendChild(close);

        const h2 = document.createElement('h2');
        h2.textContent = title;
        modalContent.appendChild(h2);

        const tableContainer = document.createElement('div');
        tableContainer.className = 'table-container';
        const table = document.createElement('table');
        const thead = document.createElement('thead');
        const trHead = document.createElement('tr');
        ['Índice', 'Fecha y Hora', 'Remitente', 'Destinatario', 'Asunto'].forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            trHead.appendChild(th);
        });
        thead.appendChild(trHead);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        if (emails.length) {
            emails.forEach(email => {
                const tr = document.createElement('tr');
                const indexCell = document.createElement('td');
                indexCell.textContent = email.index || 'N/A';
                tr.appendChild(indexCell);
                const cells = [
                    new Date(email.date).toLocaleString('es-ES'),
                    UtilsModule.escapeHtml(email.from || 'Desconocido'),
                    UtilsModule.escapeHtml(email.to || 'Desconocido'),
                    UtilsModule.escapeHtml(email.subject || 'Sin Asunto')
                ];
                cells.forEach(cell => {
                    const td = document.createElement('td');
                    td.textContent = cell;
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
        } else {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 5;
            td.textContent = 'No hay correos';
            tr.appendChild(td);
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        tableContainer.appendChild(table);
        modalContent.appendChild(tableContainer);
        modal.appendChild(modalContent);
        document.body.appendChild(modal);

        close.onclick = () => modal.remove();
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };
    }
};

document.addEventListener('DOMContentLoaded', () => {
    AgattaModule.init();
});