# ══════════════════════════════════════════════════
# OPERACIÓN 2 — ETL PIPELINE (LEGACY DATA INGESTION)
# Conduit Data Integration Strategy — Palantir Model
# ══════════════════════════════════════════════════
# By Bliss Systems LLC | APEX Standard

## Objetivo

Diseñar el motor de ingesta que transforma datos caóticos del mundo MEP
(PDFs escaneados, AutoCAD exports, Excel de 1999, Procore exports) en
tensores limpios utilizables por nuestro AI engine.

**Este documento se activa DESPUÉS de definir la Cuña (Operación 1).**
La cuña dicta QUÉ datos ingerimos primero.

---

## Principio Fundamental

> Palantir no vende "un dashboard bonito".
> Palantir vende "conectamos sus 47 sistemas legacy en una sola verdad".
>
> Conduit tampoco vende "un takeoff bonito".
> Conduit vende "dénos cualquier formato de plano y le devolvemos inteligencia".

---

## Tipos de Input que Conduit DEBE Aceptar

### Prioridad 1 (La Cuña — Takeoff)
| Formato | Fuente Típica | Complejidad | Sprint Target |
|---------|--------------|-------------|---------------|
| PDF vectorizado | Arquitecto / Ingeniero | Media | Sprint 1-2 |
| PDF escaneado (raster) | Oficina de permisos | Alta | Sprint 2-3 |
| Foto de teléfono | Técnico de campo | Muy Alta | Sprint 3-4 |
| DWG/DXF (AutoCAD) | Ingeniero MEP | Media | Sprint 5-6 |

### Prioridad 2 (Post-Cuña — Field & RFI)
| Formato | Fuente Típica | Complejidad | Sprint Target |
|---------|--------------|-------------|---------------|
| Excel de materiales | Proveedor local | Baja | Sprint 5 |
| CSV de estimaciones | ERP legacy | Baja | Sprint 5 |
| Procore export (API/CSV) | PM de contratista | Media | Sprint 7-8 |
| Bluebeam session data | Ingeniero | Media | Sprint 8 |

### Prioridad 3 (Expansión Enterprise)
| Formato | Fuente Típica | Complejidad | Sprint Target |
|---------|--------------|-------------|---------------|
| IFC 2x3/4.3 (BIM) | Arquitecto BIM | Alta | Sprint 11-12 |
| Revit export | Ingeniero MEP | Alta | Sprint 12-13 |
| ERP integration (API) | Sage, Viewpoint, etc. | Muy Alta | Tier 3 |

---

## Arquitectura del Pipeline ETL

```
INPUT (cualquier formato)
        │
        ▼
┌─────────────────────────┐
│  STAGE 1: INGESTOR      │
│  (formato → raw binary) │
│  • Detecta tipo MIME    │
│  • Valida integridad    │
│  • Antivirus (ClamAV)   │
│  • Almacena en MinIO    │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  STAGE 2: NORMALIZER    │
│  (raw → image layers)   │
│  • PDF → páginas PNG    │
│  • DWG → SVG/PNG        │
│  • Photo → deskew+crop  │
│  • Scan → OCR enhance   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  STAGE 3: EXTRACTOR     │
│  (image → structured)   │
│  • Claude Vision (AI)   │
│  • OCR (Tesseract)      │
│  • Symbol detection     │
│  • Scale calibration    │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  STAGE 4: ENRICHER      │
│  (raw data → domain)    │
│  • MEP classification   │
│  • Material matching    │
│  • Code compliance tag  │
│  • Confidence scoring   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  STAGE 5: VALIDATOR     │
│  (domain → verified)    │
│  • Schema validation    │
│  • Cross-reference chk  │
│  • Human-in-the-loop    │
│  • Audit trail          │
└──────────┬──────────────┘
           │
           ▼
   CONDUIT DATA LAKE
   (PostgreSQL + pgvector)
```

---

## Módulos del Pipeline (Backend)

```
backend/app/modules/plans/
├── ingestor/
│   ├── __init__.py
│   ├── mime_detector.py       # Detección de tipo de archivo
│   ├── integrity_checker.py   # Validación de integridad
│   ├── antivirus.py           # ClamAV scan (v1.0+)
│   └── storage.py             # Upload a MinIO por bucket
├── normalizer/
│   ├── __init__.py
│   ├── pdf_processor.py       # PyMuPDF → pages
│   ├── dwg_processor.py       # DWG/DXF → SVG/PNG (Prioridad 2)
│   ├── photo_processor.py     # OpenCV deskew + enhancement
│   ├── ocr_enhancer.py        # Pre-procesamiento para OCR
│   └── tile_generator.py      # Pirámide de tiles WebP
├── extractor/
│   ├── __init__.py
│   ├── vision_engine.py       # Claude Vision calls
│   ├── ocr_engine.py          # Tesseract OCR
│   ├── symbol_detector.py     # Detección de símbolos MEP
│   ├── scale_calibrator.py    # Calibración de escala del plano
│   └── text_parser.py         # Parser de bloques de texto
├── enricher/
│   ├── __init__.py
│   ├── mep_classifier.py      # Clasificación HVAC/Elec/Plumb
│   ├── material_matcher.py    # Match con catálogo M12
│   ├── code_tagger.py         # Tags de código aplicable
│   └── confidence_scorer.py   # Score por componente
└── validator/
    ├── __init__.py
    ├── schema_validator.py    # Validación Pydantic estricta
    ├── cross_reference.py     # Verificación cruzada
    └── audit_logger.py        # Registro de auditoría
```

---

## Integración con Operación 1

La Cuña (AI Takeoff) activa las siguientes etapas del ETL:

```
PILOTO CERO (Sprint 1-4):
  Solo PDF vectorizado + Foto de teléfono
  → INGESTOR (MIME + integridad)
  → NORMALIZER (PDF/Photo → PNG)
  → EXTRACTOR (Claude Vision + OCR)
  → ENRICHER (MEP classification + material match)
  → VALIDATOR (schema + confidence)
  → AI TAKEOFF OUTPUT

POST-PILOTO (Sprint 5+):
  + Excel de materiales del cliente
  + DWG/DXF de AutoCAD
  → Ampliar NORMALIZER con dwg_processor
  → Ampliar ENRICHER con catálogo expandido

ENTERPRISE (Sprint 10+):
  + Procore API integration
  + IFC/BIM files
  → Ampliar INGESTOR con API connectors
  → Ampliar NORMALIZER con BIM parser
```

---

## Métricas del Pipeline

| Métrica | Target MVP | Target v1.0 |
|---------|-----------|-------------|
| Tiempo PDF → Takeoff | <5 min (20 págs) | <3 min |
| Tiempo Foto → Takeoff | <8 min | <5 min |
| Precisión de extracción | >85% | >92% |
| Formatos soportados | PDF + Foto | + DWG + Excel |
| Throughput | 10 planos/hora | 50 planos/hora |

---

*Operación 2 v1.0 | Conduit ETL Pipeline | Bliss Systems LLC*
