# Bootstrap Prompt — Claude Code, перша сесія для CodeSensei

## Контекст

Ти підключаєшся до проєкту **CodeSensei** — self-hosted AI code reviewer, який є дипломним проєктом КПІ ФПМ (спеціальність 121, ІПЗ, бакалаврат 2026).

Особливості:

- Пояснювальна записка (диплом) пишеться **паралельно** іншими Claude-агентами, ти її не торкаєшся.
- Документація, конституція проєкту, вимоги і ADR-и живуть у `Диплом/` (батьківська папка).
- **Код продукту йде у папку `app/`** (твоя робоча директорія; зараз порожня — окрім цього файлу).
- Усі деталі реалізації будуть прописуватися через **Spec Kit** (GitHub'івський spec-driven development framework). Специфікації спершу, код потім.

## Твоє завдання у цій сесії

**Поки нічого не пиши — ані коду, ані файлової структури.** У цій першій сесії ти маєш:

1. Прочитати ключові reference-файли (нижче) і скласти ментальну модель:
   - Що таке CodeSensei і чому ми його будуємо.
   - Які архітектурні рішення вже прийняті (ADR-и).
   - Скоп MVP — що в обов'язковому, що відкладено, що явно out-of-scope.
   - Тех-стек.

2. Підтвердити розуміння — у відповіді сформулювати:
   - Опис продукту в 3 реченнях.
   - Перелік MUST-фіч MVP.
   - Перелік OUT-OF-SCOPE.
   - Прийняті ADR-и (по одному рядку).
   - Open decisions, які ще треба закрити перед першим коммітом.

3. Чекати наступної сесії з налаштуванням Spec Kit і написанням специфікацій.

## Файли для читання (у такому порядку)

1. `../_mvp_scope.md` — single source of truth по тому, що будуємо.
2. `../_decision_log.md` — прийняті ADR-и (ADR-001..ADR-006).
3. `../_requirements.md` — оригінальні функціональні і нефункціональні вимоги (з Notion).
4. `../_constitution.md` — процесні правила проєкту. Релевантне для тебе — §6 (Decision Log) і §1 (workflow). Решта — про написання диплому, можеш пропустити.
5. `../Аналіз рішень AI Code Reviewer.docx` — research-чернетка Розділу 1. Скімни поверхнево: тут аналіз конкурентів (CodeRabbit, PR-Agent, Greptile, SonarQube, Tabby) і обґрунтування технічних виборів (AST chunking, pgvector, RAG-стратегія).

**Пропусти:** `../chapters/`, `../temp/`, `../_agents/`, `../skills/`, `../Дипломи інших студентів 25-26/`, `../додатки з продметів...` — це для процесу написання диплому, не для коду.

## Тех-стек (зафіксовано)

- **Backend:** Python 3.12+ + FastAPI, SQLAlchemy 2.x async, alembic, asyncpg.
- **Frontend:** Vue.js 3 SPA (Vite build, віддається через nginx).
- **Database:** PostgreSQL 16 з pgvector extension (HNSW індекс на embeddings).
- **Queue:** arq + Redis для async-тасків (індексація йде десятками хвилин).
- **Deployment:** docker-compose, single command (`docker-compose up`).
- **Контейнери:** api, frontend, postgres, redis, опційно ollama.
- **AI Providers (pluggable):**
  - LLM: OpenAI (default), Anthropic, Ollama.
  - Embeddings: OpenAI `text-embedding-3-small` (default), `sentence-transformers` локально (e.g., `BAAI/bge-m3`).

## Differentiator і позиціонування

- **Architectural moat:** self-hosted persistent indexing у одному `docker-compose up`. На ринку: PR-Agent — stateless OSS, CodeRabbit/Greptile — stateful SaaS. Self-hosted + stateful — порожня клітинка, ми її займаємо.
- **Bot-mode posting:** окремий GitHub-юзер (`codesensei-bot`) з fine-grained PAT. Не GitHub App, не user-PAT, не pending-review (всі викинуті зі scope).
- **Style Calibration через GitHub reactions** — наш differentiator post-MVP, у nice-to-have. Зараз НЕ в роботі.

## Робочий процес

- **Spec-driven**: кожна нетривіальна підсистема має специфікацію перед реалізацією. Spec Kit структурує цей процес.
- **ADR-driven**: усі архітектурні рішення фіксуються в `../_decision_log.md`. Не приймай мовчазних архітектурних виборів — флагай і питай.
- **Scope changes** — через `../_mvp_scope.md`. Якщо feature з nice-to-have піднімається до MUST — це окреме рішення.
- У `app/` поки що нічого не створюй (крім цього файлу, який я вже залишив).

## Формат відповіді

У відповіді — українською — дай:

1. **Опис продукту** (3 речення): що CodeSensei робить і у чому його унікальність.
2. **MUST для MVP** (6-10 буллетів).
3. **OUT-OF-SCOPE** (4-6 буллетів — те, що явно не робимо).
4. **Прийняті ADR-и** (рядок на кожен, ADR-001..ADR-006).
5. **Open decisions** перед першим коммітом (2-5 буллетів — речі, де ще треба зробити вибір: AST parser library, queue lib, frontend bundler, logging stack, migrations strategy).
6. **Питання, якщо щось суперечливе або незрозуміле** в source-файлах (1 речення; якщо все ОК — пиши «питань нема»).

Після відповіді — **чекай**. Не пропонуй архітектуру, не пиши код, не створюй файлову структуру в `app/`, не bootstrap'ай Spec Kit. Це наступний крок разом.

---

> Цей файл — meta для процесу. Зберегти у `app/` як reference. Не вилучати після MVP — він задає контракт першої сесії з Claude Code.
