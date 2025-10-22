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
            <p>Total TODOs: ${stats.total_todos}</p>
            <p>Completados: ${stats.completed}</p>
        `;
    }
};

// Inicializar el módulo al cargar el script
document.addEventListener('DOMContentLoaded', () => {
    AgattaModule.init();
});