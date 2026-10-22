/**
 * Axx Mobile · Taller Visual MAGIC PEN
 * Implementa lienzo multitáctil con soporte de lápiz y dedo, capas independientes
 * (marcas de usuario vs respuestas de Axx), herramientas de trazo y selección,
 * acciones contextuales (texto, tablas con procedencia celda a celda, máscaras EDITAR/PROTEGER,
 * cotas y mediciones sobre planos, conteo de símbolos) y comparador de variantes.
 */

(function (global) {
  'use strict';

  class MagicPenWorkshop {
    constructor() {
      this.isOpen = false;
      this.activeTool = 'lasso'; // 'select' | 'lasso' | 'point' | 'pen' | 'highlighter' | 'arrow' | 'measure' | 'mask_edit' | 'mask_protect' | 'eraser'
      this.activeLayer = 'user'; // 'user' | 'axx'
      this.selections = []; // Lista de selecciones activas [ { id: 'A', type: 'image', bounds: {}, data: {} } ]
      this.activeSelectionId = null;
      this.undoStack = [];
      this.redoStack = [];
      this.strokes = []; // Trazos del usuario
      this.axxAnnotations = []; // Capa de Axx: regiones numeradas, flechas, contornos
      this.sourceContext = {
        name: 'Cava_Vino_Final.png',
        revision: 'Rev. 3',
        type: 'image', // 'image' | 'table' | 'document' | 'blueprint'
        width: 1920,
        height: 1080
      };

      // Máscara de edición y protección
      this.editMaskPaths = [];
      this.protectMaskPaths = [];
      this.maskBrushSize = 24;

      // Datos de tabla extraída con procedencia celda a celda
      this.extractedTable = {
        headers: ['Elemento', 'Lectura Original', 'Valor Corregido', 'Procedencia Doc'],
        rows: [
          { item: 'Altura Cava', original: '2,40 m', corrected: '2,40 m', source: 'Plano_Pág4: [x:120, y:340, w:80, h:30]', verified: true },
          { item: 'Ancho Módulo', original: '1,80 m', corrected: '1,85 m', source: 'Plano_Pág4: [x:210, y:340, w:75, h:30]', verified: true },
          { item: 'Acabado Madera', original: 'Roble Americano', corrected: 'Roble Americano Oscuro', source: 'Ficha_Técnica_Pág2: [x:40, y:180]', verified: true },
          { item: 'Deducción Puerta', original: '1,00 m²', corrected: '1,00 m²', source: 'Cuadro_Carpintería: [x:310, y:80]', verified: true }
        ],
        selectedCell: null
      };

      // Mediciones y cotas sobre planos
      this.measurements = {
        grossArea: 12.0, // m²
        deductionArea: 1.0, // m²
        netArea: 11.0, // m²
        perimeter: 14.0, // m
        scale: '1:50',
        points: []
      };

      // Conteo de símbolos por ejemplo
      this.symbolCount = {
        target: 'Puerta Tipo D01–D05',
        confirmed: 5,
        candidates: 0,
        pagesInspected: ['Pág. 4', 'Pág. 12']
      };

      // Comparador de variantes
      this.compareSplit = 50; // porcentaje
      this.compareMode = 'split'; // 'split' | 'diff' | 'toggle'

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
          console.error('Error en listener de MagicPen', e);
        }
      }
    }

    open(sourceInfo = null) {
      this.isOpen = true;
      if (sourceInfo) {
        this.sourceContext.name = sourceInfo.source || this.sourceContext.name;
        this.sourceContext.type = sourceInfo.type || 'image';
      }

      // Inicializar selecciones predeterminadas de ejemplo si está vacío
      if (this.selections.length === 0) {
        this.selections = [
          {
            id: 'A',
            label: 'Zona Madera Cava',
            type: 'image',
            color: '#B8AAFF',
            actionReady: true,
            notes: 'Cambio de acabado: roble oscuro preservando elementos protegidos.'
          },
          {
            id: 'B',
            label: 'Muro y Cotas Nivel 1',
            type: 'blueprint',
            color: '#9CE5D3',
            actionReady: true,
            notes: 'Área 12 m² brutos con 1 m² de deducción = 11 m² netos.'
          }
        ];
        this.activeSelectionId = 'A';
      }

      // Anotaciones visuales que Axx dibuja en respuesta
      if (this.axxAnnotations.length === 0) {
        this.axxAnnotations = [
          { id: 'axx-1', type: 'region', number: 1, label: 'Zona a Editar', x: 180, y: 140, r: 45, color: '#B8AAFF' },
          { id: 'axx-2', type: 'region', number: 2, label: 'Zona Protegida (Cristal)', x: 260, y: 170, r: 35, color: '#9CE5D3' },
          { id: 'axx-3', type: 'arrow', from: { x: 150, y: 100 }, to: { x: 180, y: 130 }, text: 'Verificar veta horizontal' }
        ];
      }

      this.emit('workshop-opened', { source: this.sourceContext, selections: this.selections });
    }

    close() {
      this.isOpen = false;
      this.emit('workshop-closed', {});
    }

    setTool(tool) {
      this.activeTool = tool;
      this.emit('tool-changed', { tool });
    }

    selectChip(chipId) {
      this.activeSelectionId = chipId;
      const sel = this.selections.find(s => s.id === chipId);
      this.emit('selection-focused', sel);
    }

    addStroke(stroke) {
      this.strokes.push(stroke);
      this.undoStack.push({ type: 'stroke', stroke });
      this.redoStack = [];
      this.emit('canvas-updated', { strokes: this.strokes });
    }

    undo() {
      if (this.undoStack.length === 0) return;
      const last = this.undoStack.pop();
      this.redoStack.push(last);
      if (last.type === 'stroke') {
        this.strokes.pop();
      }
      this.emit('canvas-updated', { strokes: this.strokes });
    }

    redo() {
      if (this.redoStack.length === 0) return;
      const item = this.redoStack.pop();
      this.undoStack.push(item);
      if (item.type === 'stroke') {
        this.strokes.push(item.stroke);
      }
      this.emit('canvas-updated', { strokes: this.strokes });
    }

    // Acción contextual: Convertir lo marcado en Tarea Ejecutable de Axx
    convertSelectionToTask(selectionId) {
      const sel = this.selections.find(s => s.id === selectionId) || this.selections[0];
      const task = {
        id: 'task-' + Date.now(),
        title: `Corregir y aplicar: ${sel.label}`,
        origin: sel.id,
        context: this.sourceContext.name,
        instruction: sel.notes || 'Aplicar cambios respetando máscaras protegidas',
        status: 'pending',
        evidence: 'screenshot-mark-' + Date.now() + '.png',
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      this.emit('task-created-from-selection', task);
      return task;
    }

    // Acción contextual: Guía visual paso a paso ("Muéstrame cómo hacerlo")
    startStepByStepGuide() {
      const steps = [
        { step: 1, target: 'Zona A', instruction: 'Axx señala el tirador superior. Comprueba que el tornillo esté oculto.', completed: false },
        { step: 2, target: 'Zona B', instruction: 'Ajusta el valor de holgura en 4 mm en la barra de propiedades.', completed: false },
        { step: 3, target: 'Verificación', instruction: 'Axx comprueba el contraste del resultado antes de cerrar la entrega.', completed: false }
      ];
      this.emit('visual-guide-started', { steps });
      return steps;
    }

    // Acción contextual: Seleccionar celda en tabla para ver su procedencia
    inspectCellProvenance(rowIndex, colIndex) {
      this.extractedTable.selectedCell = { row: rowIndex, col: colIndex };
      const row = this.extractedTable.rows[rowIndex];
      this.emit('cell-provenance-selected', {
        item: row.item,
        original: row.original,
        corrected: row.corrected,
        sourceDoc: row.source
      });
    }

    // Acción contextual: Corregir valor en tabla de procedencia
    updateCellValue(rowIndex, newValue) {
      if (this.extractedTable.rows[rowIndex]) {
        this.extractedTable.rows[rowIndex].corrected = newValue;
        this.extractedTable.rows[rowIndex].verified = true;
        this.emit('table-updated', this.extractedTable);
      }
    }

    // Ajustar deslizador de comparación de variantes (0 a 100)
    setCompareSplit(percentage) {
      this.compareSplit = Math.max(0, Math.min(100, percentage));
      this.emit('compare-split-changed', { split: this.compareSplit });
    }
  }

  global.AxxMagicPen = new MagicPenWorkshop();
})(typeof window !== 'undefined' ? window : this);
