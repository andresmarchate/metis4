const AgattaModule = {
    init() {
        console.log('AgattaModule initializing');
        this.agattaSection = document.getElementById('agatta-section');
        this.agattaContent = document.getElementById('agatta-content');
        if (!this.agattaSection) {
            console.error('Agatta section element not found (#agatta-section)');
        }
        if (!this.agattaContent) {
            console.error('Agatta content element not found (#agatta-content)');
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
    }
};

document.addEventListener('DOMContentLoaded', () => {
    AgattaModule.init();
});