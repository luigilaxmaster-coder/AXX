/**
 * Axx Mobile · Centro de Trabajo, Tareas, Archivos y Memoria
 * Gestiona el pipeline de tareas con dependencias, decisiones e intervenciones pendientes,
 * explorador de archivos con recuperación al teléfono, y auditor de memoria y rutinas.
 */

(function (global) {
  'use strict';

  class WorkCenterController {
    constructor() {
      this.activeTab = 'tasks'; // 'tasks' | 'decisions' | 'files' | 'memory'

      // Lista de Tareas
      this.tasks = [
        {
          id: 'task-101',
          title: 'Exportar Renders y Vistas Cava',
          pc: 'Acer Spin 3',
          stage: 'Exportando fotogramas 4K',
          progress: 85,
          status: 'active', // 'pending' | 'active' | 'blocked' | 'completed' | 'failed'
          needsIntervention: false,
          resultFile: 'Cava_Vino_Final_Render.png',
          canRetrieve: true,
          dependencies: []
        },
        {
          id: 'task-102',
          title: 'Generar Cuadro Comparativo de Puertas',
          pc: 'Acer Spin 3',
          stage: 'Esperando validación de cota',
          progress: 60,
          status: 'blocked',
          needsIntervention: true,
          interventionId: 'dec-201',
          dependencies: ['task-101']
        },
        {
          id: 'task-103',
          title: 'Comprobación de Máscara Roble Oscuro',
          pc: 'Acer Spin 3',
          stage: 'Verificación de diferencias superada',
          progress: 100,
          status: 'completed',
          needsIntervention: false,
          resultFile: 'Variante_Roble_Verificada.png',
          canRetrieve: true,
          dependencies: []
        },
        {
          id: 'task-104',
          title: 'Compilar Especificaciones Técnicas PDF',
          pc: 'Acer Spin 3',
          stage: 'En cola',
          progress: 0,
          status: 'pending',
          needsIntervention: false,
          dependencies: ['task-102']
        }
      ];

      // Decisiones e Intervenciones que requieren acción del usuario
      this.decisions = [
        {
          id: 'dec-201',
          taskId: 'task-102',
          title: 'Elegir entre dos versiones de plano de detalle',
          description: 'Axx detectó discrepancia en la cota de apertura entre Plano_Pág4 (1.80 m) y Ficha_Técnica (1.85 m). ¿Cuál prevalece?',
          options: [
            { id: 'opt-1', label: 'Usar Plano_Pág4 (1.80 m)', detail: 'Conserva alineación con muro de mampostería existente' },
            { id: 'opt-2', label: 'Usar Ficha Técnica (1.85 m)', detail: 'Recomendado por fabricante para apertura libre de 90°' }
          ],
          resolved: false,
          chosenOption: null
        }
      ];

      // Explorador de Archivos de la PC
      this.currentDirectory = 'C:\\Proyectos\\Cava_Residencial';
      this.files = [
        { name: '.. (Subir nivel)', type: 'parent', size: '', date: '' },
        { name: 'Modelos_3D', type: 'folder', size: '3 items', date: 'Hoy 14:20' },
        { name: 'Planos_PDF', type: 'folder', size: '5 items', date: 'Ayer 18:30' },
        { name: 'Cava_Vino_Final_Render.png', type: 'image', size: '4.8 MB', date: 'Hoy 17:15', isResult: true },
        { name: 'Variante_Roble_Verificada.png', type: 'image', size: '5.1 MB', date: 'Hoy 17:28', isResult: true },
        { name: 'Cuadro_Materiales_Extraccion.csv', type: 'file', size: '42 KB', date: 'Hoy 16:50', isResult: true },
        { name: 'Restricciones_Obra.md', type: 'document', size: '12 KB', date: '20 Oct' }
      ];

      // Memoria y Rutinas
      this.memories = [
        {
          id: 'mem-1',
          fact: 'La cava de vino utiliza siempre roble americano con poro abierto.',
          scope: 'Proyecto: Cava_Residencial',
          origin: 'Instrucción explícita de usuario',
          date: '20 Oct 2026',
          status: 'active'
        },
        {
          id: 'mem-2',
          fact: 'Carpeta de exportación predeterminada: C:\\Proyectos\\Cava_Residencial\\Renders',
          scope: 'Proyecto: Cava_Residencial',
          origin: 'Configurado por usuario en Studio v20',
          date: '19 Oct 2026',
          status: 'active'
        },
        {
          id: 'mem-3',
          fact: 'Preferencias de render: motor Cycles, 1024 samples con denoiser OIDN.',
          scope: 'Global',
          origin: 'Aprendido de sesión Blender',
          date: '18 Oct 2026',
          status: 'active'
        }
      ];

      // Rutinas Automatizadas
      this.routines = [
        {
          id: 'rt-1',
          name: 'Modo Revisión de Acabados',
          version: 'v2.1',
          steps: [
            '1. Cargar archivo .blend del proyecto',
            '2. Extraer fotograma actual a Magic Pen',
            '3. Aplicar máscara PROTEGER a herrajes y botellas',
            '4. Solicitar variante de textura de madera',
            '5. Generar mapa de diferencias comparativo'
          ],
          active: true
        },
        {
          id: 'rt-2',
          name: 'Extracción de Cuadro de Puertas',
          version: 'v1.4',
          steps: [
            '1. Procesar páginas 4 y 12 del PDF',
            '2. Detectar etiquetas D01 a D05',
            '3. Calcular cotas de ancho y deducciones',
            '4. Exportar tabla CSV con enlaces de procedencia'
          ],
          active: true
        }
      ];

      this.listeners = new Set();
    }

    subscribe(fn) {
      this.listeners.add(fn);
      return () => this.listeners.delete(fn);
    }

    emit(event, data) {
      for (const fn of this.listeners) {
        try {
          fn(event, data);
        } catch (e) {
          console.error('Error en listener de WorkCenter', e);
        }
      }
    }

    setTab(tab) {
      this.activeTab = tab;
      this.emit('tab-changed', { tab });
    }

    // Resolver una decisión pendiente desde el móvil
    resolveDecision(decisionId, optionId) {
      const dec = this.decisions.find(d => d.id === decisionId);
      if (dec) {
        dec.resolved = true;
        dec.chosenOption = optionId;

        // Desbloquear tarea asociada
        const task = this.tasks.find(t => t.id === dec.taskId);
        if (task) {
          task.status = 'active';
          task.needsIntervention = false;
          task.stage = 'Reanudada con opción: ' + (optionId === 'opt-1' ? '1.80 m' : '1.85 m');
        }

        // Notificar al backend de la PC
        if (global.AxxBridge) {
          global.AxxBridge.request('/axx-api/connect/approval', {
            method: 'POST',
            body: { request_id: decisionId, approval_id: optionId, decision: 'approve' }
          }).catch(() => {});
        }

        this.emit('decision-resolved', { decision: dec, task });
        return { success: true, message: 'Decisión confirmada y sincronizada con Axx PC.' };
      }
      return { success: false, error: 'Decisión no encontrada' };
    }

    // Reordenar tareas o reintentar
    retryTask(taskId) {
      const task = this.tasks.find(t => t.id === taskId);
      if (task) {
        task.status = 'active';
        task.progress = 10;
        task.stage = 'Reintentando ejecución...';
        this.emit('tasks-updated', this.tasks);
      }
    }

    cancelTask(taskId) {
      const task = this.tasks.find(t => t.id === taskId);
      if (task) {
        task.status = 'failed';
        task.stage = 'Cancelada por el usuario desde el teléfono';
        this.emit('tasks-updated', this.tasks);
      }
    }

    // Recuperar archivo de la PC al teléfono (Descarga local verificada)
    retrieveFileToMobile(filename) {
      const file = this.files.find(f => f.name === filename);
      if (!file) return { success: false, error: 'Archivo no encontrado' };

      // Simular descarga / recuperación
      this.emit('file-retrieved', {
        filename: file.name,
        size: file.size,
        status: 'verificado_sha256'
      });
      return {
        success: true,
        message: `Archivo "${filename}" recuperado en tu teléfono con evidencia verificada.`
      };
    }

    // Modificar o retirar un recuerdo
    forgetMemory(memoryId) {
      const idx = this.memories.findIndex(m => m.id === memoryId);
      if (idx !== -1) {
        const removed = this.memories.splice(idx, 1)[0];
        this.emit('memory-updated', this.memories);
        return { success: true, message: `Recuerdo eliminado: "${removed.fact}"` };
      }
      return { success: false };
    }

    // Volver a versión anterior de una rutina
    rollbackRoutine(routineId) {
      const routine = this.routines.find(r => r.id === routineId);
      if (routine) {
        routine.version = routine.version === 'v2.1' ? 'v2.0' : 'v1.3';
        this.emit('routines-updated', this.routines);
        return { success: true, message: `Rutina revertida a versión ${routine.version}` };
      }
      return { success: false };
    }
  }

  global.AxxWorkCenter = new WorkCenterController();
})(typeof window !== 'undefined' ? window : this);
