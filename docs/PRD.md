# Personal Finance Tracker - Product Requirements Document (PRD)

**Version:** 1.0
**Date:** 2026-02-11
**Author:** Jose
**Status:** Draft

---

## 1. Executive Summary

### 1.1 Problem Statement
Currently lacking visibility into personal spending patterns. Bank statements provide raw transaction data but no easy way to analyze spending by custom categories over specific time periods.

### 1.2 Solution Overview
A web-based personal finance application that allows importing bank transaction data (via CSV), categorizing expenses, and visualizing spending patterns over configurable date ranges.

### 1.3 Success Criteria
- Able to categorize 100% of imported transactions
- Generate spending reports by category within 5 seconds
- System handles at least 1,000 transactions without performance degradation

---

## 2. Goals & Objectives

### 2.1 Primary Goals
1. **Visibility**: See total spending by custom categories between any two dates
2. **Categorization**: Assign transactions to user-defined categories efficiently
3. **Data Import**: Easy upload of bank transaction data

### 2.2 Non-Goals (Out of Scope for v1.0)
- Direct bank API integration
- Multi-user support / shared accounts
- Budget planning or forecasting
- Mobile native apps (web-responsive is sufficient)
- Integration with accounting software
- Bill payment or reminders
- Investment tracking

---

## 3. User Personas

### 3.1 Primary User: Jose (The Power User)
- **Background**: Technical professional, comfortable with exports/imports
- **Goals**: Detailed spending analysis, custom categorization
- **Pain Points**: Existing tools too complex or don't support custom categories
- **Technical Comfort**: High - willing to export CSVs manually

---

## 4. User Stories

### 4.1 Must Have (MVP)

#### Epic 1: Data Management
```
As a user
I want to upload my bank transaction CSV file
So that I can analyze my spending

Acceptance Criteria:
- System accepts CSV files up to 5MB
- Supports common date formats (DD/MM/YYYY, YYYY-MM-DD)
- Validates required fields (date, description, amount)
- Shows preview of imported data before saving
- Prevents duplicate imports (same date + amount + description)
```

```
As a user
I want to create and manage spending categories
So that I can organize my expenses meaningfully

Acceptance Criteria:
- Create categories with custom names and colors
- Edit existing category names
- Delete categories (with warning if transactions assigned)
- Cannot delete category if transactions are assigned to it
- Default categories suggested: Groceries, Dining, Transport, Utilities, Entertainment, Healthcare, Shopping, Other
```

#### Epic 2: Transaction Categorization
```
As a user
I want to manually assign categories to transactions
So that I can organize my spending

Acceptance Criteria:
- View list of uncategorized transactions
- Select transaction and assign category via dropdown
- Bulk selection to assign multiple transactions at once
- See visual indicator for categorized vs uncategorized
- Filter view by categorized/uncategorized status
```

```
As a user
I want to create auto-categorization rules
So that I don't have to manually categorize recurring transactions

Acceptance Criteria:
- Create rules based on transaction description (contains text)
- Rules auto-apply to new imports
- Option to apply rules retroactively to existing transactions
- View and manage all active rules
- Rule priority/order when multiple rules match
```

#### Epic 3: Reporting & Visualization
```
As a user
I want to see total spending by category for a date range
So that I understand where my money goes

Acceptance Criteria:
- Select start and end date (default: current month)
- Display total per category in a table
- Show percentages of total spending
- Pie chart visualization of spending distribution
- Bar chart showing spending per category
- Include/exclude specific categories from view
```

```
As a user
I want to see spending trends over time
So that I can identify patterns

Acceptance Criteria:
- Line chart showing total spending per month
- Compare current month vs previous month
- Category breakdown per month (stacked bar chart)
- Export report data to CSV
```

### 4.2 Should Have (Future Versions)
- Income vs Expense tracking
- Search/filter transactions by description
- Multi-account support
- Recurring transaction detection
- Budget setting per category

### 4.3 Nice to Have
- Mobile responsive design improvements
- Dark mode
- Currency conversion for foreign transactions
- Scheduled imports (if API integration added)
- PDF export of reports

---

## 5. Functional Requirements

### 5.1 Data Import
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | System shall accept CSV file uploads | Must Have |
| FR-1.2 | System shall validate CSV format and required columns | Must Have |
| FR-1.3 | System shall detect and prevent duplicate transactions | Must Have |
| FR-1.4 | System shall show import preview before confirming | Should Have |
| FR-1.5 | System shall log import history (date, file, record count) | Should Have |

### 5.2 Category Management
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | User shall be able to create custom categories | Must Have |
| FR-2.2 | User shall be able to edit category names and colors | Must Have |
| FR-2.3 | User shall be able to delete unused categories | Must Have |
| FR-2.4 | System shall prevent deletion of categories with assigned transactions | Must Have |
| FR-2.5 | System shall provide default category templates | Should Have |

### 5.3 Transaction Categorization
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | User shall be able to manually assign categories to transactions | Must Have |
| FR-3.2 | User shall be able to bulk-assign categories | Should Have |
| FR-3.3 | User shall be able to create auto-categorization rules | Should Have |
| FR-3.4 | System shall apply rules automatically on import | Should Have |
| FR-3.5 | User shall be able to modify transaction category after assignment | Must Have |

### 5.4 Reporting
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | User shall be able to select custom date ranges | Must Have |
| FR-4.2 | System shall display total spending per category | Must Have |
| FR-4.3 | System shall show percentage breakdown | Must Have |
| FR-4.4 | System shall generate pie chart visualization | Must Have |
| FR-4.5 | System shall generate bar chart visualization | Must Have |
| FR-4.6 | System shall support CSV export of reports | Should Have |

---

## 6. Non-Functional Requirements

### 6.1 Performance
| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1.1 | Page load time | < 2 seconds |
| NFR-1.2 | Report generation time | < 5 seconds for 1,000 transactions |
| NFR-1.3 | CSV import processing | < 10 seconds for 1,000 rows |
| NFR-1.4 | Database query response | < 1 second |

### 6.2 Usability
| ID | Requirement |
|----|-------------|
| NFR-2.1 | Interface shall be intuitive for non-technical users |
| NFR-2.2 | Application shall work on desktop browsers (Chrome, Firefox, Safari, Edge) |
| NFR-2.3 | Mobile responsive layout (minimum viewport: 375px) |
| NFR-2.4 | Color-blind friendly visualizations |

### 6.3 Security
| ID | Requirement |
|----|-------------|
| NFR-3.1 | Data stored locally (no cloud upload in v1.0) |
| NFR-3.2 | No authentication required (single-user local app) |
| NFR-3.3 | Input validation on all user-provided data |
| NFR-3.4 | Protection against CSV injection attacks |

### 6.4 Reliability
| ID | Requirement |
|----|-------------|
| NFR-4.1 | Data persistence (survive browser refresh) |
| NFR-4.2 | Graceful error handling with user-friendly messages |
| NFR-4.3 | Data backup/export capability |

---

## 7. Technical Specifications

### 7.1 Technology Stack (Proposed)
- **Frontend**: HTML5, CSS3, JavaScript (vanilla or lightweight framework)
- **Backend**: Python Flask or Node.js Express
- **Database**: SQLite (local file-based)
- **Charting**: Chart.js or D3.js
- **CSV Parsing**: PapaParse (JS) or Python csv module

### 7.2 Database Schema (Preliminary)

```sql
-- Categories Table
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transactions Table
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    description TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    category_id INTEGER,
    import_batch_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Auto-categorization Rules
CREATE TABLE categorization_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    priority INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Import History
CREATE TABLE import_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    records_imported INTEGER,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.3 CSV Format Expected

```csv
Date,Description,Amount,Balance
01/02/2026,GROCERY STORE XYZ,-45.32,1234.56
02/02/2026,SALARY DEPOSIT,2500.00,3734.56
03/02/2026,RESTAURANT ABC,-67.89,3666.67
```

**Required Columns:**
- Date (flexible format, will parse)
- Description (transaction text)
- Amount (negative for expenses, positive for income)

**Optional Columns:**
- Balance (can be ignored)
- Transaction ID (for duplicate detection)

---

## 8. User Interface Mockups

### 8.1 Key Screens

1. **Dashboard** (Home)
   - Quick stats: Total spending this month, most expensive category
   - Recent uncategorized transactions alert
   - Quick access buttons: Import, Categorize, View Reports

2. **Import Screen**
   - Drag-and-drop CSV upload
   - CSV preview table
   - Column mapping (if headers don't match expected)
   - Import confirmation

3. **Categorization Screen**
   - Left panel: Transaction list (filterable)
   - Right panel: Category selector
   - Bulk actions toolbar
   - Progress indicator (X of Y categorized)

4. **Category Management**
   - List of categories with usage counts
   - Add/Edit/Delete buttons
   - Color picker for each category

5. **Reports Screen**
   - Date range selector (with presets: This Month, Last Month, Last 3 Months, YTD, Custom)
   - Summary table (Category | Amount | Percentage)
   - Pie chart
   - Bar chart
   - Export button

---

## 9. Dependencies & Assumptions

### 9.1 Dependencies
- User can export CSV from their bank
- User has basic computer literacy (file upload, form filling)
- Modern web browser with JavaScript enabled

### 9.2 Assumptions
- Single user (no concurrent access needed)
- Bank CSV format remains consistent
- English language only for v1.0
- Desktop-first usage (mobile secondary)

---

## 10. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| CSV format varies by bank | High | High | Flexible parser, column mapping feature |
| Date format inconsistencies | Medium | High | Multiple date format support, validation |
| Large file performance | Medium | Low | Pagination, lazy loading, file size limits |
| Data loss | High | Low | Export backup feature, browser local storage |
| Browser compatibility | Medium | Medium | Progressive enhancement, feature detection |

---

## 11. Open Questions

1. Should we support multiple accounts (e.g., checking + credit card)?
   - **Decision needed by:** Before development starts
   - **Recommendation:** Not for v1.0, but design DB schema to allow future expansion

2. How to handle split transactions (one transaction, multiple categories)?
   - **Decision needed by:** Before v1.0 release
   - **Recommendation:** Defer to v2.0

3. Currency support (single vs multi-currency)?
   - **Decision needed by:** Before development starts
   - **Recommendation:** Single currency (EUR) for v1.0

---

## 12. Timeline & Milestones (Estimated)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1: Setup & Data Import | 1 week | CSV upload + parsing working |
| Phase 2: Categorization | 1 week | Manual categorization + category CRUD |
| Phase 3: Rules Engine | 3 days | Auto-categorization rules |
| Phase 4: Reporting | 1 week | Date filtering + charts |
| Phase 5: Polish & Testing | 3 days | UI improvements, bug fixes |
| **Total** | **~4 weeks** | **MVP Release** |

---

## 13. Success Metrics

### 13.1 Launch Criteria
- [ ] Import 100 transactions successfully
- [ ] Create 10 custom categories
- [ ] Categorize all transactions
- [ ] Generate report for current month
- [ ] All charts rendering correctly
- [ ] Zero critical bugs

### 13.2 Post-Launch Metrics (Personal Use)
- Time saved per month vs manual spreadsheet tracking
- Percentage of transactions auto-categorized (target: >60% after 3 months)
- Frequency of use (target: weekly)

---

## 14. Approval & Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product Owner | Jose | 2026-02-11 | _________ |
| Developer | Jose | 2026-02-11 | _________ |

---

## Appendix A: Glossary

- **CSV**: Comma-Separated Values file format
- **Transaction**: A single bank account entry (debit or credit)
- **Category**: User-defined spending classification
- **Auto-categorization**: Automatic assignment based on rules
- **Import Batch**: A single CSV file upload session

---

## Appendix B: References

- PSD2 Banking API Standards: https://www.europeanpaymentscouncil.eu/
- Chart.js Documentation: https://www.chartjs.org/
- SQLite Documentation: https://www.sqlite.org/

---

**Document History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-11 | Jose | Initial draft |
