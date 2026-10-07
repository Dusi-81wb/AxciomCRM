# AcxiomCRM — Master Blueprint

## 1. Project Definition

### 1.1 Project Name

**AcxiomCRM**

### 1.2 Project Purpose

AcxiomCRM is a role-based Customer Relationship Management system designed to manage:

- Users and roles
- Customers
- Leads
- Opportunities
- Follow-ups
- Activities
- Dashboard KPIs
- Reports
- Audit logs
- REST API access

The system must demonstrate more than basic CRUD.

It must demonstrate:

- Authentication
- Authorization
- Role-based access control
- Ownership-based access
- Server-side validation
- Client-side validation
- Business-rule validation
- Secure password handling
- Account lockout
- Audit logging
- Dashboard reporting
- Search and filtering
- REST API
- Proper layered architecture
- Automated tests

The project must remain simple enough for a student developer to explain every important file, function, database table, request flow, and security decision.

---

# 2. Source of Truth

The following files are the authoritative project design documents:

```text
MASTER_BLUEPRINT.md
SPECIFICATION_NOTES.md

Before implementing any phase:
1. Read MASTER_BLUEPRINT.md.
2. Read SPECIFICATION_NOTES.md.
3. Follow the decisions recorded there.
4. Do not silently change architecture, technology, scope, or business rules.
5. If an ambiguity is discovered, stop and ask for clarification.
6. Approved decisions must be recorded in SPECIFICATION_NOTES.md.
The supplied assignment document remains the original functional source.
The blueprint translates those requirements into an implementable student-friendly architecture.
3. Fixed Technology Stack
The implementation uses the following stack.
3.1 Backend
Python
Flask

Flask will use the application-factory pattern.
3.2 Database
PostgreSQL
psycopg2

The project will use direct SQL through psycopg2.
No ORM is used.
3.3 Frontend
HTML
CSS
JavaScript
Jinja2
Bootstrap

3.4 Charts
Chart.js

3.5 Security
Werkzeug password hashing
Flask-WTF CSRF
Flask-Limiter
Flask sessions

3.6 Testing
pytest

4. Technology Caveat
The assignment contains ASP.NET Core-specific requirements in some sections.
Examples include:
- ASP.NET Core Identity
- Entity Framework Core
- MVC anti-forgery mechanisms
- Razor validation
The implementation stack selected for this project is Flask + PostgreSQL.
Therefore equivalent Flask mechanisms will be used.
Examples:
Assignment Concept	AcxiomCRM Implementation
ASP.NET Core Identity	Flask authentication + PostgreSQL user table + Werkzeug hashing
Identity password hashing	Werkzeug password hashing
Identity roles/claims	Application RBAC
Authentication cookies	Flask secure session cookie
MVC anti-forgery	Flask-WTF CSRF
EF Core parameterization	psycopg2 parameterized SQL
Razor validation	HTML/JavaScript validation + server validation
ASP.NET authorization	Flask decorators + service/repository ownership checks


No ASP.NET-specific library will be introduced.
A clarification may be requested from the evaluator regarding whether these technology-equivalent implementations are acceptable.
5. Core Architectural Principle
The project follows strict layered architecture.
Browser
   ↓
Routes / Controllers
   ↓
Services
   ↓
Repositories
   ↓
PostgreSQL

Supporting layers:
Security
Schemas
Validation
Models
Templates
Static JavaScript/CSS

6. Layer Responsibilities
6.1 Routes
Routes are responsible for:
- Receiving HTTP requests
- Reading form/query/path parameters
- Authentication checks
- Authorization decorators
- Calling services
- Returning HTML responses
- Returning JSON API responses
Routes must NOT contain:
- SQL
- Business calculations
- Complex business rules
- Direct database transactions
Example:
POST /customers/create
        ↓
customer_route
        ↓
customer_service.create_customer()

7. Services
Services contain application and business logic.
Services are responsible for:
- Business rules
- Workflow logic
- Authorization decisions that require business context
- Transactions
- Calling repositories
- Calling audit services
- Coordinating multiple repository operations
Example:
customer_service.create_customer()

may:
1. Validate input.
2. Check duplicate customer.
3. Check authorization.
4. Create customer.
5. Create audit entry.
6. Commit transaction.
8. Repositories
Repositories contain all SQL.
No SQL should exist in:
- Routes
- Templates
- Services
- Security modules
Repositories are responsible for:
- SELECT
- INSERT
- UPDATE
- DELETE
- Search
- Filtering
- Pagination
- Aggregation queries
All user-controlled SQL values must use parameterized queries.
Example:
cursor.execute(    """    SELECT *    FROM customers    WHERE email = %s    """,    (email,))


Never construct SQL by concatenating user input.
9. Schemas
Schemas handle field-level validation.
Examples:
- Required fields
- Email format
- Phone format
- String lengths
- Numeric format
- Date format
Schemas do NOT replace business rules.
10. Business Validation
Business rules are implemented in:
validation/business_rules.py

Examples:
Opportunity amount > 0
Probability between 0 and 100
Active opportunity close date cannot be in the past
Follow-up date cannot be before today
Valid lead status transitions

Field validation and business validation must remain conceptually separate.
11. Security Layer
Security-related code belongs in:
security/

The security layer handles:
- Authentication
- Current-user loading
- Role checks
- Authorization decorators
- Session handling
- Ownership checks
Security decisions must never depend only on frontend controls.
12. Project Structure
The final project structure is:
AcxiomCRM/
│
├── app.py
├── config.py
├── database.py
├── extensions.py
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
│
├── README.md
├── API.md
├── SPECIFICATION_NOTES.md
├── MASTER_BLUEPRINT.md
│
├── routes/
│   ├── auth_routes.py
│   ├── dashboard_routes.py
│   ├── customer_routes.py
│   ├── lead_routes.py
│   ├── opportunity_routes.py
│   ├── followup_routes.py
│   ├── activity_routes.py
│   ├── user_routes.py
│   ├── audit_routes.py
│   ├── report_routes.py
│   └── api_routes.py
│
├── models/
│   ├── user.py
│   ├── role.py
│   ├── customer.py
│   ├── lead.py
│   ├── opportunity.py
│   ├── followup.py
│   ├── activity.py
│   └── audit_log.py
│
├── services/
│   ├── auth_service.py
│   ├── customer_service.py
│   ├── lead_service.py
│   ├── opportunity_service.py
│   ├── followup_service.py
│   ├── activity_service.py
│   ├── user_service.py
│   ├── audit_service.py
│   ├── dashboard_service.py
│   └── report_service.py
│
├── repositories/
│   ├── user_repository.py
│   ├── customer_repository.py
│   ├── lead_repository.py
│   ├── opportunity_repository.py
│   ├── followup_repository.py
│   ├── activity_repository.py
│   └── audit_repository.py
│
├── schemas/
│   ├── customer_schema.py
│   ├── lead_schema.py
│   ├── opportunity_schema.py
│   ├── followup_schema.py
│   ├── activity_schema.py
│   └── api_schema.py
│
├── security/
│   ├── authentication.py
│   ├── authorization.py
│   └── decorators.py
│
├── validation/
│   └── business_rules.py
│
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   │
│   ├── errors/
│   │
│   ├── dashboard/
│   ├── customers/
│   ├── leads/
│   ├── opportunities/
│   ├── followups/
│   ├── activities/
│   ├── users/
│   ├── roles/
│   ├── audit/
│   └── reports/
│
├── static/
│   ├── css/
│   │   └── style.css
│   │
│   └── js/
│       ├── validation.js
│       ├── dashboard.js
│       └── filters.js
│
├── sql/
│   ├── schema.sql
│   └── seed.sql
│
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_customers.py
    ├── test_leads.py
    ├── test_opportunities.py
    ├── test_followups.py
    ├── test_activities.py
    ├── test_authorization.py
    ├── test_audit.py
    ├── test_api.py
    ├── test_dashboard.py
    ├── test_reports.py
    └── test_business_rules.py

13. Application Factory
The application must use:
create_app()


The application factory is responsible for:
- Creating Flask application
- Loading configuration
- Initializing extensions
- Registering blueprints/routes
- Registering error handlers
- Setting security configuration
The application should be started through:
app.py

14. Extensions
Common Flask extensions belong in:
extensions.py

Expected extensions include:
- CSRF protection
- Rate limiting
Do not create unnecessary security abstraction layers.
15. Configuration
Configuration must be centralized.
Important configuration values include:
DATABASE_URL
SECRET_KEY
SESSION_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY
SESSION_COOKIE_SAMESITE
PASSWORD_MIN_LENGTH
MAX_LOGIN_ATTEMPTS
LOCKOUT_DURATION
APPLICATION_TIMEZONE
RATE_LIMITS

Secrets must come from environment variables.
Secrets must never be hard-coded into source code.
16. Environment Files
The project contains:
.env
.env.example

.env contains local development secrets.
.env.example documents required variables without real secrets.
.env must be excluded from Git.
17. Database
PostgreSQL is the only application database.
All database access must go through:
database.py
repositories/

18. Database Connection Management
database.py should provide simple connection management.
The implementation must make transaction boundaries understandable.
Services own transactions.
A normal business operation should follow:
Service starts operation
        ↓
Repository operations
        ↓
Audit operation
        ↓
Commit

If a required operation fails:
Rollback

19. Database Entities
The database must support the following core entities.
19.1 User
User records must support:
- UserId
- Username
- Email
- PasswordHash
- IsActive
- FailedLoginAttempts
- LockoutUntil
- CreatedDate
- ModifiedDate
- LastLoginDate
- RoleId
Passwords must never be stored in plaintext.
20. Role
The required primary roles are:
Admin
Manager
Sales Executive

A normal user has exactly one primary role.
Multi-role users are not required.
21. Customer
Required fields:
CustomerId
CustomerCode
CustomerName
Email
Phone
CompanyName
Address
City
State
Status
AssignedTo
CreatedDate
ModifiedDate
CreatedBy

Customer status must support the required business states.
Customer ownership must be enforceable.
22. Lead
Required fields:
LeadId
LeadCode
LeadName
Email
Phone
CompanyName
Source
Status
ExpectedValue
CreatedDate
ModifiedDate
AssignedTo

Required lead statuses:
New
Contacted
Qualified
Unqualified
Converted
Lost

23. Opportunity
Required fields:
OpportunityId
OpportunityName
CustomerId
LeadId
Amount
Stage
Probability
ExpectedCloseDate
Status
CreatedDate
ModifiedDate
ClosedDate
AssignedTo

24. Opportunity Stage
Required stages:
Qualification
Proposal
Negotiation
Won
Lost

25. Opportunity Status
Opportunity status is separate from stage.
Allowed status values:
Open
Won
Lost

An active opportunity is:
Status = Open

A won opportunity:
Status = Won
Stage = Won

A lost opportunity:
Status = Lost
Stage = Lost

26. Follow-Up
Required fields:
FollowUpId
CustomerId
LeadId
OpportunityId
Subject
FollowUpDate
FollowUpType
Remarks
Status
AssignedTo
CreatedDate
ModifiedDate

Follow-up status:
Planned
Completed
Missed
Cancelled

A follow-up must relate to the appropriate CRM record.
27. Activity
Required fields:
ActivityId
ActivityType
Subject
Description
ActivityDate
CustomerId
LeadId
AssignedTo
Status
CreatedDate
ModifiedDate

Activities support the CRM activity history required by the assignment.
28. AuditLog
Required fields:
AuditLogId
UserId
Action
EntityName
RecordId
OldValue
NewValue
Result
CreatedDate
IpAddress

OldValue and NewValue may use PostgreSQL JSONB.
Sensitive information must never be stored in audit metadata.
Never store:
- Passwords
- Password hashes
- Session tokens
- API secrets
- Authentication tokens
29. Database Constraints
Database constraints should enforce fundamental data integrity where practical.
Examples:
Probability >= 0
Probability <= 100
Amount >= 0
Required foreign keys
Unique customer codes
Unique lead codes

Business rules that require current date or workflow context remain service-level rules.
30. Database Indexes
Indexes should be created for commonly searched fields.
Examples:
Customer.Email
Customer.Phone
Customer.AssignedTo

Lead.Status
Lead.AssignedTo
Lead.Email

Opportunity.Stage
Opportunity.Status
Opportunity.AssignedTo
Opportunity.ExpectedCloseDate

FollowUp.FollowUpDate
FollowUp.Status
FollowUp.AssignedTo

AuditLog.UserId
AuditLog.EntityName
AuditLog.Action
AuditLog.CreatedDate

Only useful indexes should be created.
31. Soft Deactivation
Historical CRM records must remain meaningful.
Users should be deactivated rather than physically deleted where historical references require the user.
Inactive users cannot log in.
Inactive users cannot be assigned new CRM records.
Existing historical records remain intact.
32. Customer Duplicate Rules
Customer duplicate detection must consider relevant identity fields such as:
Email
Phone

Inactive customer contact information remains reserved.
The system must not casually allow duplicate identities merely because a customer is inactive.
33. Authentication
Authentication must support:
- Register
- Login
- Logout
- Session management
- Password hashing
- Password policy
- Failed-login tracking
- Account lockout
34. Registration
Public registration creates a standard CRM user.
Every self-registered user must receive:
Sales Executive

The user cannot select:
Admin
Manager

during registration.
Administrative role assignment is restricted to authorized administrators.
35. Password Hashing
Passwords must be hashed using Werkzeug's secure password hashing functions.
Example concept:
generate_password_hash()check_password_hash()


Never store plaintext passwords.
Never return password hashes through:
- HTML
- API
- Logs
- Audit metadata
36. Password Policy
Password policy must enforce the configured minimum security requirements.
At minimum:
- Minimum length
- Required secure format
- No empty password
The exact policy must be centralized in configuration.
37. Login Security
Login should:
1. Find the user.
2. Check account status.
3. Check lockout.
4. Verify password.
5. Reset failed attempts on success.
6. Record last login.
7. Create secure session.
8. Audit successful login.
Failed authentication should:
1. Increment failed attempts.
2. Potentially lock the account.
3. Audit the failure.
4. Return a generic error.
The user must not receive messages that reveal whether the username or email exists.
Use:
Invalid credentials

as the generic login error.
38. Session Security
After successful login:
session.clear()


must be performed before establishing the authenticated session state.
Session configuration should use:
HTTPOnly
SameSite
Secure where HTTPS is available

Do not store passwords or sensitive secrets in the session.
39. Current User Loading
For every protected request:
1. Read the user identity from the session.
2. Load the user from PostgreSQL.
3. Verify that the account still exists.
4. Verify is_active.
5. Use the current database role.
Never trust a role stored only in the session.
This ensures that an administrator can deactivate or change a user's role and the change takes effect on subsequent requests.
40. Account Lockout
The system must support:
FailedLoginAttempts
LockoutUntil

The threshold and duration must be configurable.
Example flow:
Failed attempt
      ↓
Increment counter
      ↓
Threshold reached?
      ↓
Yes
      ↓
Set LockoutUntil

Successful login resets failed attempts.
Administrators can unlock accounts.
Lockout and unlock actions must be audited.
41. Authorization
Authorization uses:
Role-based access control
+
Ownership-based access control

The frontend must never be the security boundary.
42. Role Permissions
Admin
Admin has full access to:
- Users
- Roles
- Customers
- Leads
- Opportunities
- Follow-ups
- Activities
- Reports
- Audit logs
- Dashboard
- Security administration
Manager
Manager has access to:
- CRM management
- Team/customer data
- Leads
- Opportunities
- Follow-ups
- Activities
- Reports
- Dashboard
- Pipeline information
Manager must not have unrestricted security administration.
Sales Executive
Sales Executive has access to:
- Assigned customers
- Assigned leads
- Assigned opportunities
- Assigned follow-ups
- Relevant activities
- Relevant reports
- Personal dashboard
Sales Executive cannot access unrestricted administrator functionality.
43. Ownership Enforcement
Ownership must be enforced in SQL.
Do not:
SELECT all records
↓
filter them in Python

Instead use SQL conditions.
Example:
SELECT *
FROM opportunities
WHERE assigned_to = %s

This is important because authorization must happen before unauthorized records reach application logic.
44. Manager Scope
The assignment requires manager/team-level CRM visibility but does not completely define the organizational team model.
For the initial implementation:
Manager scope = CRM records visible to the manager according to the centralized visibility function.

A helper such as:
visible_user_ids(user)

should centralize this decision.
If the evaluator defines a more specific team relationship, the implementation can be adjusted in one place.
Do not scatter manager-scope logic throughout repositories.
45. Security Rules
The application must enforce:
- Authentication
- Authorization
- Password hashing
- Lockout
- CSRF protection
- Secure sessions
- Parameterized SQL
- Server validation
- Ownership validation
- Audit logging
- Rate limiting
46. CSRF Protection
All state-changing browser requests must be protected.
Examples:
POST
PUT
PATCH
DELETE

Use Flask-WTF CSRF protection.
The application must not disable CSRF protection simply to make a request work.
API requests should use the chosen API authentication strategy and must not incorrectly depend on browser form CSRF behavior.
47. SQL Injection Protection
All SQL values must use parameterized queries.
Never:
query = "SELECT * FROM users WHERE email = '" + email + "'"


Use:
cursor.execute(    "SELECT * FROM users WHERE email = %s",    (email,))


48. Sort and Filter Whitelisting
SQL parameters cannot safely substitute arbitrary column identifiers.
Therefore sorting fields must come from explicit whitelists.
Example:
allowed_sort_columns = {    "name": "customer_name",    "email": "email",    "created": "created_date"}


User input chooses a key.
The application chooses the actual SQL column.
49. API Security
All protected API endpoints require authentication.
API authorization must follow the same role and ownership rules as the web application.
API responses must never expose:
PasswordHash
Session information
Secrets
Internal security data
Database credentials
Stack traces

50. Audit Architecture
Audit logging is a core subsystem and must be implemented early.
Audit should not be added at the end of the project.
Each module must call the audit service when relevant actions occur.
51. Required Audit Events
Audit events include:
- Login success
- Login failure
- Logout
- User creation
- User update
- User activation
- User deactivation
- Role changes
- Password/security events
- Customer create
- Customer update
- Customer delete/deactivate
- Lead create
- Lead update
- Lead status changes
- Lead conversion
- Opportunity create
- Opportunity update
- Opportunity stage changes
- Opportunity status changes
- Follow-up create
- Follow-up completion
- Follow-up rescheduling
- Follow-up cancellation
- Activity create/update
- API security events where relevant
52. Audit Record
An audit record should contain:
User
Timestamp
Action
Module/Entity
Record ID
Result
Old Value
New Value
IP Address

Audit records are append-oriented.
Normal application users must not be able to edit historical audit entries.
The database role used for audit storage should not grant ordinary UPDATE/DELETE privileges on audit records.
53. Audit Transactions
For normal business operations:
Business change
+
Audit record

must commit together.
If the business operation fails:
Business change rollback
+
Audit rollback

Failed login and rejected-request audit events may use a separate transaction because the primary business transaction does not exist.
54. Error Handling
The application must have centralized handlers for:
400 Bad Request
403 Forbidden
404 Not Found
500 Internal Server Error

Users receive friendly messages.
Stack traces must not be displayed to users.
55. Customer Management
Customer functionality includes:
- Create
- Read
- Update
- Delete/deactivate as appropriate
- Search
- Filter
- Ownership
- Validation
- Audit history
56. Customer Fields
Customer form includes:
Customer Name
Email
Phone
Company Name
Address
City
State
Status
Assigned Sales Executive
Notes where applicable

The database model must retain the mandatory assignment fields.
57. Customer Validation
Validate:
- Required customer name
- Valid email
- Valid phone
- Appropriate field lengths
- Duplicate email/phone
- Valid assigned user
- Authorized assignment
Validation occurs on:
Client side
+
Server side

Server validation is authoritative.
58. Customer Audit
Customer creation, modification, status changes, assignment changes and deletion/deactivation must be audited.
59. Lead Management
Lead functionality includes:
- Create
- Read
- Update
- Delete/deactivate where appropriate
- Assignment
- Search
- Filtering
- Status transitions
- Conversion
- Audit
60. Lead Fields
Lead includes:
Lead Name
Email
Phone
Company Name
Source
Status
Priority where applicable
Expected Value
Assigned To
Notes

61. Lead Statuses
The functional requirement defines:
New
Contacted
Qualified
Unqualified
Converted
Lost

The Chart.js requirement specifically mentions:
New
Contacted
Qualified
Lost
Converted

The application retains all six functional statuses.
Unqualified remains a valid CRM state even if a particular chart does not display it.
62. Lead Status Transition Matrix
The proposed transition rules are:
New
 ├──> Contacted
 ├──> Unqualified
 └──> Lost

Contacted
 ├──> Qualified
 ├──> Unqualified
 └──> Lost

Qualified
 ├──> Converted
 └──> Lost

Unqualified
 └── terminal

Converted
 └── terminal

Lost
 └── terminal

Invalid transitions must be rejected by the server.
Every status change must be audited.
63. Lead Conversion
Lead conversion is a business workflow.
A conversion may:
1. Identify or create a customer.
2. Create/link an opportunity when required.
3. Update lead status to Converted.
4. Audit the conversion.
The complete conversion must occur inside one database transaction.
If any step fails:
Rollback entire conversion.

No partial conversion should remain.
64. Duplicate Customer During Lead Conversion
If an existing customer can be safely identified:
Link lead to existing customer

may be permitted.
If identity cannot be established safely:
Reject conversion

with a clear user-facing explanation.
Do not silently merge unrelated customers.
65. Opportunity Management
Opportunity functionality includes:
- Create
- Read
- Update
- Delete/close where appropriate
- Assignment
- Stage management
- Status management
- Pipeline calculation
- Search
- Filtering
- Reporting
- Audit
66. Opportunity Fields
Opportunity includes:
Opportunity Name
Customer
Lead
Owner / Assigned To
Stage
Amount
Probability
Expected Close Date
Status
Source where applicable
Notes

67. Opportunity Amount
Database:
NUMERIC(14,2)

Python:
Decimal

Never use Python float for financial amounts.
68. Opportunity Probability
Probability must satisfy:
0 <= probability <= 100

Any value outside this range must be rejected.
69. Active Opportunity Rules
For an active opportunity:
Status = Open
Amount > 0
Probability between 0 and 100
ExpectedCloseDate is not in the past

These rules must be enforced server-side.
70. Opportunity Stage/Status Rules
Stage:
Qualification
Proposal
Negotiation
Won
Lost

Status:
Open
Won
Lost

When the opportunity is won:
Stage = Won
Status = Won
ClosedDate = current business date/time

When lost:
Stage = Lost
Status = Lost
ClosedDate = current business date/time

71. Pipeline Value
Dashboard:
Total Pipeline Value
=
SUM(amount of open opportunities)

Only:
Status = Open

is included.
Weighted pipeline is calculated separately for the Pipeline Report.
72. Weighted Pipeline
Weighted pipeline:
Amount × Probability / 100

Example:
Amount = 100000
Probability = 60

Weighted Value = 60000

Weighted pipeline belongs primarily to reporting.
73. Follow-Up Management
Follow-ups may relate to:
Customer
Lead
Opportunity

Fields include:
Date
Subject
Type
Status
Remarks/Notes
Assigned User

74. Follow-Up Status
Allowed statuses:
Planned
Completed
Missed
Cancelled

75. Follow-Up Rules
The follow-up date must not be before today.
Today must be interpreted using:
Asia/Kolkata

timezone.
Completion, rescheduling and cancellation must be audited.
76. Upcoming and Overdue Follow-Ups
The application should support identifying:
Upcoming follow-ups
Overdue follow-ups
Completed follow-ups

Role/ownership rules apply.
77. Activity Management
Activities provide CRM interaction history.
Examples include:
Call
Email
Meeting
Task
Other supported activity type

Activities contain:
Activity Type
Subject
Description
Activity Date
Customer
Lead
Assigned User
Status

Activity access follows the same role/ownership rules.
78. User Management
Admin functionality includes:
- Create users
- Edit users
- Activate users
- Deactivate users
- Search users
- View account status
- View lockout status
- Reset password securely
- Assign role
- Audit user changes
79. Role Management
The system uses:
Admin
Manager
Sales Executive

The primary role is explicitly stored.
Role changes are security-sensitive operations.
Every role change must be audited.
80. User Security Information
Normal user management screens must not expose:
Password
Password hash
Session token
Security secrets

Only appropriate security/account status should be displayed.
81. Dashboard
The dashboard is role-aware.
Required KPI cards:
Total Customers
Total Leads
Open Leads
Total Opportunities
Open Opportunities
Won
Lost
Total Pipeline Value

82. Dashboard Role Scope
Admin:
Organization-wide view

Manager:
Manager/team CRM view

Sales Executive:
Assigned/personal CRM view

All dashboard queries must enforce authorization at the server.
83. Dashboard Filters
Required date filters:
Today
This Week
This Month
Custom Range

Date filtering must be performed by the backend.
Do not fetch all data and filter only in JavaScript.
84. Dashboard Date Semantics
Use the appropriate date field for each metric.
Customers
→ CreatedDate

Leads
→ CreatedDate

Opportunities
→ CreatedDate

Won/Lost
→ ClosedDate

Monthly Sales
→ ClosedDate

Follow-ups
→ FollowUpDate

Activities
→ ActivityDate

85. Dashboard Charts
Chart.js must be used.
Required charts:
Lead Status
New
Contacted
Qualified
Lost
Converted

The functional Unqualified status remains in the system.
Opportunity Pipeline
Qualification
Proposal
Negotiation
Won
Lost

Monthly Sales
Monthly sales should use completed/won opportunities and their ClosedDate.
86. Dashboard Security
Chart data must be generated using server-authorized queries.
Do not rely on hidden frontend controls to restrict dashboard data.
87. Search and Filtering
Customer search:
Name
Email
Phone
Company

Lead search:
Name
Company
Status
Assigned

Opportunity search:
Name
Customer
Stage
Status

Follow-up search:
Date
Status
Assigned
Related record

Activity search:
Type
Date
Status
Assigned

88. Reports
The system should provide the following reports:
Customer Report
Lead Report
Follow-Up Report
Opportunity Report
Pipeline Report
Sales / Conversion Report
User Activity Report
Audit Report

89. Report Features
Where appropriate, reports support:
- Filtering
- Sorting
- Pagination
- Export
Only implement export formats that are required and approved.
Do not add unrelated reporting functionality.
90. Pipeline Report
Pipeline report should provide:
Opportunity
Amount
Probability
Weighted Value
Stage
Status
Expected Close Date
Owner

Weighted value:
Amount × Probability / 100

91. Sales / Conversion Report
The sales/conversion report should support analysis of:
Leads
Converted leads
Won opportunities
Lost opportunities
Sales amounts
Conversion performance

92. Audit Report
Audit report must support filtering by:
User
Module / Entity
Action
Date

Audit data must respect security permissions.
Only authorized roles can access sensitive audit information.
93. REST API
The application must expose at least one REST API controller.
The recommended API scope is:
Customers
Leads
Opportunities

Additional endpoints should only be added where they are necessary for the assignment.
94. API Design
API routes should be under:
/api/

Example:
GET /api/customers
GET /api/customers/<id>
POST /api/customers
PUT /api/customers/<id>
DELETE /api/customers/<id>

Equivalent endpoints may be created for leads and opportunities.
95. API DTOs
Do not directly serialize database rows as unrestricted JSON.
Use explicit DTO/serializer functions.
API responses must contain only intended fields.
Never expose:
PasswordHash
Tokens
Secrets
Internal database details

96. API Validation
API input must receive server-side validation.
Invalid data must return an appropriate error response.
97. API Status Codes
The API should use:
200 OK
201 Created
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict

where appropriate.
98. API Authentication
Protected API endpoints require authentication.
Authorization must be enforced for every protected endpoint.
The API must not assume that a user is authorized simply because they are authenticated.
99. API Documentation
API documentation must be maintained in:
API.md

It should explain:
- Endpoint
- Method
- Authentication
- Parameters
- Request body
- Response
- Error codes
- Authorization behavior
100. Validation Architecture
Validation has three layers.
Client validation
        ↓
Server field validation
        ↓
Business-rule validation

Client validation improves usability.
Server validation provides security.
Business rules enforce application behavior.
101. Required Validation Rules
The system must validate:
Required fields
Email format
Phone format
String lengths
Dates
Numeric values
Foreign keys
Authorization
Business state transitions

102. Email Validation
Email must:
- Be present where required.
- Follow a valid format.
- Respect uniqueness/duplicate rules where applicable.
103. Phone Validation
Phone must:
- Follow the configured format.
- Respect length rules.
- Not contain invalid characters.
104. Date Validation
Examples:
Active opportunity close date cannot be past.
Follow-up date cannot be before today.

These checks must be performed on the server.
105. Foreign Key Validation
Before assigning:
Customer
Lead
Opportunity
User

the application must verify that the referenced record exists and is valid for the operation.
106. Unauthorized Changes
The server must reject attempts to:
- Modify another user's records without permission.
- Assign records without authorization.
- Change protected roles without permission.
- Access records outside the user's scope.
107. Friendly Errors
User-facing errors should be understandable.
Example:
Probability must be between 0 and 100.

rather than:
CHECK constraint violation 23514

Internal error details must remain in server logs only where appropriate and must not expose secrets.
108. Timezone
The business timezone is:
Asia/Kolkata

All rules involving:
today
this week
this month
past date
upcoming date

must use this timezone.
Do not depend blindly on the server's local timezone.
109. Money Handling
All monetary values must use:
PostgreSQL NUMERIC(14,2)
Python Decimal

Never use:
float

for money.
110. Transaction Ownership
Services own transactions.
A service should coordinate:
Repository operation
+
Audit operation

inside the correct transaction.
Repositories should not independently commit business operations.
111. Seed Data
The application should include realistic seed data.
Seed data must include examples of:
Admin
Manager
Sales Executive
Customers
Leads
Opportunities
Follow-ups
Activities

The seed data should demonstrate different statuses and stages.
No real personal information should be used.
112. Demo Users
A development/demo environment should contain one example user for each role:
Admin
Manager
Sales Executive

Passwords must be securely hashed.
Demo credentials must be documented only for local development/demo purposes.
113. Testing Strategy
Every phase must include tests.
Testing framework:
pytest

114. Authentication Tests
Tests should cover:
- Successful registration
- Successful login
- Failed login
- Generic invalid-credential response
- Lockout
- Lockout reset after successful login
- Logout
- Inactive-user rejection
- Session behavior
115. Customer Tests
Tests should cover:
- Create
- Read
- Update
- Delete/deactivate
- Required fields
- Invalid email
- Invalid phone
- Duplicate detection
- Ownership
- Audit
116. Lead Tests
Tests should cover:
- CRUD
- Assignment
- Search
- Status validation
- Valid transitions
- Invalid transitions
- Conversion
- Audit
117. Opportunity Tests
Tests should cover:
- CRUD
- Amount validation
- Probability validation
- Close-date validation
- Stage
- Status
- Pipeline calculation
- Ownership
- Audit
118. Follow-Up Tests
Tests should cover:
- CRUD
- Required related record
- Date validation
- Status changes
- Completion
- Rescheduling
- Ownership
- Audit
119. Activity Tests
Tests should cover:
- Create
- Read
- Update
- Status
- Date
- Ownership
- Audit
120. Authorization Tests
Tests must prove that:
Admin can access admin functionality.
Manager cannot access unrestricted security administration.
Sales Executive cannot access another user's records.
Unauthorized users receive 403.
Unauthenticated users receive 401/redirect as appropriate.

121. API Tests
API tests should cover:
- Authentication
- Authorization
- CRUD
- Validation
- Status codes
- DTO fields
- Sensitive-field exclusion
122. Dashboard Tests
Dashboard tests should verify:
- KPI calculations
- Role scope
- Date filters
- Pipeline calculation
- Chart data
- Won/lost counts
123. Report Tests
Reports should be tested for:
- Filtering
- Authorization
- Correct calculations
- Sorting
- Pagination where implemented
124. Business Rule Tests
Business-rule tests should explicitly test:
Amount <= 0
Probability < 0
Probability > 100
Past opportunity close date
Past follow-up date
Invalid lead transition
Unauthorized assignment
Duplicate customer

125. Test Philosophy
Tests should be readable by a student.
Avoid unnecessary abstraction.
Each test should make clear:
Given
When
Then

Example:
Given an active Sales Executive
When the user requests another executive's opportunity
Then the server returns forbidden

126. Documentation
The project must include:
README.md
API.md
SPECIFICATION_NOTES.md
MASTER_BLUEPRINT.md

127. README
README should explain:
- Project purpose
- Technology stack
- Setup
- PostgreSQL configuration
- Environment variables
- Database setup
- Seed data
- Running the application
- Running tests
- Demo roles
- Architecture overview
128. API Documentation
API.md documents all implemented REST API endpoints.
It must not claim endpoints that do not actually exist.
129. Specification Notes
SPECIFICATION_NOTES.md contains:
- Assignment ambiguities
- Technology substitutions
- Approved decisions
- Open questions
- Evaluator clarifications
- Important implementation assumptions
Do not silently resolve major ambiguities.
130. Code Quality
The implementation should prioritize:
Clarity
Correctness
Security
Explainability
Maintainability

over:
Clever abstractions
Over-engineering
Unnecessary design patterns

131. Code Style
Prefer:
- Plain functions
- Clear names
- Small modules
- Explicit control flow
- Short services
- Simple SQL
- Comments explaining non-obvious decisions
Avoid unnecessary:
- Generic repositories
- Generic services
- Dependency injection frameworks
- Metaprogramming
- Complex decorators
- Excessive inheritance
132. Request Flow
A normal browser request should follow:
Browser
  ↓
Route
  ↓
Authentication
  ↓
Authorization
  ↓
Schema validation
  ↓
Service
  ↓
Business rules
  ↓
Repository
  ↓
PostgreSQL
  ↓
Audit
  ↓
Commit
  ↓
Service result
  ↓
Route
  ↓
Jinja template
  ↓
Browser

133. API Request Flow
API request:
Client
  ↓
API Route
  ↓
Authentication
  ↓
Authorization
  ↓
Schema validation
  ↓
Service
  ↓
Business rules
  ↓
Repository
  ↓
PostgreSQL
  ↓
DTO serializer
  ↓
JSON response

134. Login Flow
Login Form
   ↓
POST /login
   ↓
Validate input
   ↓
Find user
   ↓
Check active
   ↓
Check lockout
   ↓
Check password
   ↓
Success?
   ├── No → increment attempts → audit → generic error
   │
   └── Yes
          ↓
      reset attempts
          ↓
      update last login
          ↓
      audit
          ↓
      create session
          ↓
      dashboard

135. Customer Creation Flow
POST /customers/create
        ↓
CSRF validation
        ↓
Authentication
        ↓
Authorization
        ↓
Field validation
        ↓
Business validation
        ↓
Duplicate check
        ↓
Repository INSERT
        ↓
Audit INSERT
        ↓
COMMIT
        ↓
Redirect to customer list

136. Lead Conversion Flow
Convert Lead
     ↓
Authorization
     ↓
Validate lead
     ↓
Check lead status
     ↓
Find/create customer
     ↓
Create opportunity if required
     ↓
Update lead
     ↓
Create audit records
     ↓
COMMIT

If any operation fails:
ROLLBACK

137. Opportunity Flow
Create Opportunity
        ↓
Validate customer/lead
        ↓
Validate amount
        ↓
Validate probability
        ↓
Validate expected close date
        ↓
Validate authorization
        ↓
INSERT
        ↓
Audit
        ↓
Commit

138. Dashboard Flow
GET /dashboard
      ↓
Authentication
      ↓
Load current DB user
      ↓
Determine role scope
      ↓
Apply date filter
      ↓
Dashboard service
      ↓
Repository aggregation queries
      ↓
KPI data
      ↓
Chart data
      ↓
Jinja + Chart.js

139. Application Scope
The application must implement the assignment's required CRM functionality.
The project is NOT intended to become a general-purpose enterprise CRM.
140. Explicit Non-Scope
Do not add the following unless explicitly approved:
React
Vue
Angular
FastAPI
Django
SQLAlchemy
Other ORM
Redis
Celery
RabbitMQ
Kafka
WebSockets
JWT authentication
Microservices
AI features
Chatbots
LLM integrations
Vector databases
Payment systems
Email automation
SMS automation
Mobile application
Native desktop application
Blockchain
Unrelated analytics

Do not add features merely because they are technically interesting.
141. No Scope Creep
If a feature is not required by the assignment or this blueprint:
Do not implement it.

If the feature appears useful but is not clearly required:
Ask first.

142. Phase Development Strategy
Development happens in controlled phases.
Do not build the entire project at once.
Each phase must:
1. Read the blueprint.
2. Implement only its defined scope.
3. Write tests.
4. Run tests.
5. Produce an explanation report.
6. Produce traceability.
7. Identify deviations/open questions.
8. Stop and wait for review.
143. Phase 0 — Specification Verification and Foundation
Scope:
- Verify blueprint
- Verify specification notes
- Create project skeleton
- Create app factory
- Create configuration
- Create database connection foundation
- Create extensions
- Create requirements
- Create environment template
- Create basic documentation
- Establish testing foundation
Do not implement CRM modules yet.
144. Phase 1 — PostgreSQL Foundation
Scope:
- Create database schema
- Create tables
- Create constraints
- Create foreign keys
- Create indexes
- Create seed data
- Verify database connectivity
Tests:
- Database connection
- Schema integrity
- Seed data availability
145. Phase 2 — Authentication
Scope:
- Registration
- Login
- Logout
- Password hashing
- Password policy
- Session handling
- Failed attempts
- Lockout
- Account activation check
Tests:
- Registration
- Login
- Invalid credentials
- Lockout
- Logout
- Session
146. Phase 3 — RBAC and Audit
Scope:
- Roles
- Authorization
- Ownership foundation
- Current-user loading
- Audit infrastructure
- Audit repository
- Audit service
- Audit security
Tests:
- Role access
- Ownership
- Unauthorized access
- Audit creation
147. Phase 4 — Application Shell
Scope:
- Base template
- Navigation
- Flash messages
- Error pages
- Global error handlers
- Common CSS
- Authentication-aware UI
148. Phase 5 — Customer Management
Scope:
- Customer CRUD
- Search
- Filters
- Validation
- Ownership
- Audit
- Server-side validation
Tests:
test_customers.py

149. Phase 6 — Lead Management
Scope:
- Lead CRUD
- Search
- Filters
- Assignment
- Status transitions
- Conversion workflow
- Audit
Tests:
test_leads.py

150. Phase 7 — Opportunity Management
Scope:
- Opportunity CRUD
- Stage
- Status
- Amount
- Probability
- Expected close date
- Pipeline
- Ownership
- Audit
Tests:
test_opportunities.py
test_business_rules.py

151. Phase 8 — Follow-Ups and Activities
Scope:
- Follow-up CRUD
- Follow-up validation
- Follow-up status
- Upcoming/overdue
- Activities
- Audit
Tests:
test_followups.py
test_activities.py

152. Phase 9 — User and Role Administration
Scope:
- User list
- Create user
- Edit user
- Activate/deactivate
- Role assignment
- Secure password reset
- Account lockout management
- Audit
Tests:
test_authorization.py
test_auth.py

153. Phase 10 — Dashboard
Scope:
- KPI cards
- Role-based scope
- Date filters
- Lead Status chart
- Opportunity Pipeline chart
- Monthly Sales chart
- Chart.js integration
Tests:
test_dashboard.py

154. Phase 11 — Reports
Scope:
- Customer report
- Lead report
- Follow-up report
- Opportunity report
- Pipeline report
- Sales/conversion report
- User activity report
- Audit report
- Filtering
- Sorting
- Pagination where required
- Export only where approved
Tests:
test_reports.py

155. Phase 12 — REST API
Scope:
- API controller/routes
- Customer API
- Lead API
- Opportunity API
- DTOs
- Authentication
- Authorization
- Validation
- Status codes
- API documentation
Tests:
test_api.py

156. Phase 13 — Integration and Security Testing
Verify:
- Authentication
- Authorization
- Ownership
- CSRF
- SQL injection protection
- Validation
- Business rules
- Audit
- API
- Dashboard
- Reports
- Error handling
Run the complete pytest suite.
157. Phase 14 — Acceptance Testing
The final system must demonstrate the required acceptance scenario.
158. Acceptance Scenario 1 — Anonymous Access
Attempt to access a protected page while logged out.
Expected:
Access denied or redirect to login.

159. Acceptance Scenario 2 — Registration/Login
Register a valid user.
Expected:
Sales Executive role

Then log in.
Expected:
Dashboard displayed.

160. Acceptance Scenario 3 — Invalid Customer
Submit invalid customer data through the browser.
Expected:
Client-side validation

Then bypass client-side validation.
Expected:
Server rejects invalid data.

161. Acceptance Scenario 4 — Invalid Opportunity Amount
Try:
Amount <= 0

Expected:
Server rejects the opportunity.

162. Acceptance Scenario 5 — Invalid Probability
Try:
Probability > 100

Expected:
Server rejects the opportunity.

163. Acceptance Scenario 6 — Past Close Date
Try creating an active opportunity with a past close date.
Expected:
Server rejects it.

164. Acceptance Scenario 7 — Past Follow-Up
Try creating a follow-up before today.
Expected:
Server rejects it.

165. Acceptance Scenario 8 — Sales Executive Ownership
Login as Sales Executive.
Attempt to access another executive's record.
Expected:
403 Forbidden

or an equivalent secure denial.
166. Acceptance Scenario 9 — Manager
Login as Manager.
Expected:
Team/manager CRM visibility
Pipeline access
Reports
Dashboard

Manager must not gain unrestricted security administration.
167. Acceptance Scenario 10 — Admin
Login as Admin.
Expected access to:
Users
Roles
Audit
CRM
Reports
Dashboard
Security administration

168. Acceptance Scenario 11 — CRUD Audit
Create/update a CRM record.
Expected:
Business operation succeeds
+
Audit record created

169. Acceptance Scenario 12 — API
Call:
/api/customers

Expected:
Authenticated JSON response

No password hashes or sensitive information should appear.
170. Acceptance Scenario 13 — Dashboard
Dashboard must display:
Total Customers
Total Leads
Open Leads
Total Opportunities
Open Opportunities
Won
Lost
Total Pipeline Value

and required Chart.js visualizations.
171. Traceability
Every requirement implemented must be traceable to:
Requirement
↓
File
↓
Function
↓
Test

Example:
Opportunity probability 0–100
→ validation/business_rules.py
→ validate_probability()
→ tests/test_business_rules.py

172. Requirement-to-Code Principle
Do not implement functionality without knowing:
Why it exists
Which requirement requires it
Where it is implemented
How it is tested

This is necessary for project demonstration and viva/interview explanation.
173. Final Demonstration Flow
The final demonstration should follow a realistic CRM workflow:
Open application
      ↓
Attempt anonymous access
      ↓
Register Sales Executive
      ↓
Login
      ↓
View dashboard
      ↓
Create customer
      ↓
Create lead
      ↓
Change lead status
      ↓
Convert lead
      ↓
Create opportunity
      ↓
Demonstrate validation
      ↓
Create follow-up
      ↓
Complete follow-up
      ↓
View pipeline
      ↓
View reports
      ↓
View audit
      ↓
Login as Manager
      ↓
Show role-based scope
      ↓
Login as Admin
      ↓
Show user/role/security management
      ↓
Call REST API

174. Student Explainability Requirement
Every implementation decision must be explainable by the student.
The student should be able to answer:
Why Flask?
Why PostgreSQL?
Why psycopg2?
Why parameterized SQL?
Why services?
Why repositories?
Why password hashing?
Why sessions?
Why CSRF?
Why RBAC?
Why ownership checks?
Why audit logs?
Why Decimal?
Why server-side validation?
Why Chart.js?
Why DTOs?
Why transactions?

The implementation must therefore favor straightforward code.
175. Final Quality Standard
The project is complete only when all of the following are demonstrated:
✓ Authentication
✓ Secure password hashing
✓ Password policy
✓ Lockout
✓ Session security
✓ RBAC
✓ Ownership authorization
✓ Customer CRUD
✓ Lead CRUD
✓ Lead workflow
✓ Lead conversion
✓ Opportunity CRUD
✓ Opportunity business rules
✓ Pipeline
✓ Follow-ups
✓ Activities
✓ User administration
✓ Audit logging
✓ Dashboard
✓ Chart.js
✓ Search/filter
✓ Reports
✓ REST API
✓ DTOs
✓ Client validation
✓ Server validation
✓ Business validation
✓ CSRF protection
✓ Parameterized SQL
✓ Error handling
✓ Automated tests
✓ Documentation

176. Strict Development Rules
Antigravity/developer must obey these rules throughout the project.
Rule 1
Do not change the technology stack without explicit approval.
Rule 2
Do not introduce an ORM.
Rule 3
Do not put SQL inside routes.
Rule 4
Do not put SQL inside templates.
Rule 5
Do not perform authorization only in JavaScript.
Rule 6
Do not trust role information stored only in the session.
Rule 7
Do not use floating-point numbers for monetary values.
Rule 8
Do not concatenate user input into SQL.
Rule 9
Do not expose password hashes.
Rule 10
Do not expose stack traces to users.
Rule 11
Do not silently resolve major specification conflicts.
Rule 12
Do not add unnecessary features.
Rule 13
Do not refactor previous phases without approval.
Rule 14
Do not skip tests.
Rule 15
Do not move to the next phase until the current phase is reviewed.
177. Required Phase Completion Report
At the end of every phase, produce:
A. Phase Summary
Explain exactly what was implemented.
B. Files Created
List every new file.
C. Files Modified
List every modified file.
D. Function Explanation
Explain every important function.
E. Request Flow
Explain how requests move through:
Route
→ Service
→ Repository
→ Database

F. Security Explanation
Explain security decisions implemented in the phase.
G. Tests
Show:
pytest command

and actual results.
H. Traceability
Provide:
Requirement
→ File
→ Function
→ Test

I. Deviations
List every deviation from the blueprint.
J. Open Questions
List anything requiring clarification.
Then stop.
Do not continue automatically to the next phase.
178. Final Architecture Summary
The final architecture should remain understandable as:
                    ┌───────────────────┐
                    │      Browser      │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Routes / API      │
                    │ Controllers       │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Security          │
                    │ Authentication    │
                    │ Authorization     │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Schemas           │
                    │ Validation        │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Services          │
                    │ Business Logic    │
                    │ Transactions      │
                    │ Audit Coordination │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Repositories      │
                    │ All SQL           │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ PostgreSQL        │
                    └───────────────────┘

Supporting components:
Models
Templates
Static JS/CSS
Chart.js
Tests
Documentation

179. Final Principle
AcxiomCRM must remain:
Simple enough to explain.
Secure enough to demonstrate.
Structured enough to look professional.
Complete enough to satisfy the assignment.
Small enough to avoid unnecessary complexity.

The goal is not to build the largest CRM possible.
The goal is to build the required CRM correctly, securely, testably, and in a way that the student can confidently explain every important part of the system