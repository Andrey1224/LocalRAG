# Markdown Files Classification for LocalRAG

## 📚 **MUST COMMIT** - Core Documentation

### Project Documentation
- ✅ `README.md` - Main project documentation
- ✅ `CLAUDE.md` - Development guide for Claude Code
- ✅ `.gitignore-guide.md` - Git ignore documentation

### Architecture & Planning
- ✅ `DEVELOPMENT_PLAN.md` - Project roadmap and milestones
- ✅ `PROJECT_INFO.md` - High-level project information

### Product Requirements Documents (PRDs)
- ✅ `PRD_ASK.md` - Ask endpoint requirements
- ✅ `PRD_DOCKER_DEPLOY_ENV.md` - Deployment requirements
- ✅ `PRD_EVALRUN.md` - Evaluation requirements
- ✅ `PRD_FEEDBACK.md` - Feedback system requirements
- ✅ `PRD_INGEST.md` - Document ingestion requirements
- ✅ `PRD_LOGGING_MONITORING.md` - Logging requirements

### UI Documentation
- ✅ `BASIC_UI.md` - UI specifications

## 🚫 **SHOULD NOT COMMIT** - Temporary/Generated

### Testing Reports (Temporary)
- ❌ `TESTING_REPORT.md` - Temporary testing results
- ❌ `test_results_*.md` - Test execution results
- ❌ `test_analysis_summary.md` - Analysis summaries
- ❌ `pattern_analysis.md` - Code pattern analysis

### Support Files (Temporary)
- ❌ `support_agent_knowledge_base*.md` - Temporary support docs
- ❌ `test_document.md` - Test content files

## 🔄 **CONDITIONAL** - Case by Case

### Documentation in Development
- 🔍 Check if it's part of permanent project documentation
- 🔍 If it contains temporary data/results → Don't commit
- 🔍 If it's reusable project knowledge → Commit

## ✅ **Current .gitignore Rules for .md files:**

```gitignore
# Temporary analysis and testing files
*_REPORT.md
*test_results*.md
*test_analysis*.md
*pattern_analysis*.md

# Temporary test content
test_document.md

# Support documentation (temporary)
support_agent_knowledge_base*.md
*knowledge_base*.md
```

## 🛠️ **How to Decide:**

### ✅ Commit if:
- Part of project documentation
- Contains reusable knowledge
- Needed by team members
- Describes architecture/requirements
- Will be referenced in future

### ❌ Don't commit if:
- Contains test results/outputs
- Generated automatically
- Contains temporary data
- Personal notes/drafts
- Will become outdated quickly

## 🔍 **Check Before Committing:**

```bash
# See all .md files status
git status | grep "\.md"

# Check if specific file should be ignored
git check-ignore filename.md

# Add specific .md file to commit
git add specific-file.md
```
