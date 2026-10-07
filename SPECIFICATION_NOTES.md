
# AcxiomCRM — Specification Notes

## 1. Purpose of This File

This file records important specification decisions, ambiguities, technology substitutions, assumptions, and clarifications for the AcxiomCRM project.

It exists alongside:

```text
MASTER_BLUEPRINT.md

The assignment document is the original functional source.
MASTER_BLUEPRINT.md converts the assignment into the implementation architecture.
SPECIFICATION_NOTES.md records decisions made while resolving ambiguities.
2. Source Documents
The primary functional source is:
AcxiomCRM — Functional & Technical Project Documentation

The project requirements include:
- Authentication
- Authorization
- Dashboard
- Customer Management
- Lead Management
- Follow-Up Management
- User & Role Management
- Opportunity Management
- Audit Log
- REST API
- Reports
- Validation
- Security
- Role-based access
- Business rules
- Testing
- Layered architecture
3. Technology Decision — ASP.NET vs Flask
Assignment Requirement
The assignment contains ASP.NET Core-specific requirements including concepts such as:
- ASP.NET Core Identity
- Entity Framework Core
- Identity password hashing
- Identity claims/roles
- Authentication cookies
- MVC anti-forgery
- Razor/client validation
Project Decision
The implementation will use:
Python
Flask
PostgreSQL
psycopg2
Jinja
HTML/CSS/JavaScript
Bootstrap
Chart.js
Werkzeug password hashing
Flask-WTF CSRF
Flask-Limiter
pytest

No ASP.NET Core implementation will be introduced.
Equivalent Mapping
Assignment Requirement	Implementation
ASP.NET Core Identity	Flask authentication + PostgreSQL user system
Identity password hashing	Werkzeug password hashing
Identity roles/claims	Application RBAC
Identity authentication cookies	Flask secure session cookie
MVC anti-forgery	Flask-WTF CSRF
Entity Framework Core	Direct PostgreSQL access through psycopg2
EF parameterization	psycopg2 parameterized SQL
Razor validation	HTML/JavaScript + server-side validation


Important
This is a technology substitution and should be clarified with the evaluator before final submission if required.
Do not silently claim that Flask is ASP.NET Core.
4. Lead Status Discrepancy
Functional Requirement
The lead workflow defines:
New
Contacted
Qualified
Unqualified
Converted
Lost

Dashboard Chart Requirement
The Chart.js Lead Status requirement specifically mentions:
New
Contacted
Qualified
Lost
Converted

Unqualified is not explicitly listed in that chart requirement.
Decision
The application will retain all six functional lead statuses:
New
Contacted
Qualified
Unqualified
Converted
Lost

The chart may display the statuses explicitly required by the chart specification.
Unqualified remains a valid business status even if it is not displayed in that particular chart.
Reason
The functional CRM requirement is broader than the chart display requirement.
Removing Unqualified would contradict the lead workflow requirement.
5. Lead Status Transition Decision
The assignment requires valid lead transitions but does not provide a complete transition matrix.
The following transition matrix is adopted:
New
 ├── Contacted
 ├── Unqualified
 └── Lost

Contacted
 ├── Qualified
 ├── Unqualified
 └── Lost

Qualified
 ├── Converted
 └── Lost

Unqualified
 └── terminal

Converted
 └── terminal

Lost
 └── terminal

Invalid transitions must be rejected by the server.
Every valid status change must be audited.
If the evaluator specifies a different transition matrix, update this file before changing implementation.
6. REST API Scope Discrepancy
Assignment Requirement
The assignment requires:
- At least one API controller
- Secure endpoints
- DTOs
- Validation
- Authentication
- Authorization
- Documentation
- Appropriate HTTP status codes
The assignment recommends API support for:
Customers
Leads
Opportunities

Decision
The implementation will provide REST API support for:
Customers
Leads
Opportunities

The API will use DTO/serializer functions.
The API will not expose:
PasswordHash
Passwords
Session data
Authentication tokens
Secrets
Internal security details
Database credentials

Additional API endpoints will not be added unless necessary.
7. Manager Team Scope
Assignment Requirement
The Manager role is described as having team-level CRM visibility.
However, the assignment does not define a complete organizational team model.
There is no mandatory team table specified.
Decision
Manager visibility will be centralized through a visibility function such as:
visible_user_ids(user)

The initial implementation will treat Manager CRM visibility as the manager's permitted team/CRM scope.
This decision must not be scattered across individual repositories.
If the evaluator defines an explicit team relationship, the visibility implementation can be updated centrally.
8. Delete vs Historical Auditability
Assignment Requirement
The assignment requires CRUD operations and auditability.
Hard deletion can conflict with historical references and audit interpretation.
Decision
Where historical records depend on the entity:
Deactivate / soft-delete

is preferred over physical deletion.
Historical CRM records should remain understandable.
Examples:
Inactive user
Inactive customer
Inactive CRM assignment

The system must not destroy historical information merely to satisfy a CRUD label.
Where physical deletion is implemented, it must not violate foreign-key integrity or historical audit requirements.
9. Customer AssignedTo Field
Assignment Database Entity
The mandatory Customer entity fields listed in the assignment include:
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
CreatedDate
CreatedBy

Functional Requirement
The Customer Management functionality also requires assignment to a Sales Executive.
Decision
The Customer table additionally contains:
AssignedTo
ModifiedDate

This is required to support:
- Sales Executive ownership
- Role-based visibility
- Assignment
- Dashboard scope
- Manager visibility
- Auditability
10. Follow-Up Entity Fields
Assignment Entity Definition
The database FollowUp entity includes:
FollowUpId
CustomerId
LeadId
FollowUpDate
FollowUpType
Remarks
Status
AssignedTo

Functional Requirement
Follow-ups also require:
- Opportunity relationship
- Subject
- Notes/details
- Assignment
- Status
Decision
The FollowUp table additionally contains:
OpportunityId
Subject
CreatedDate
ModifiedDate

This allows the implementation to satisfy both the entity definition and functional workflow requirements.
11. Opportunity Stage vs Status
The assignment specifies opportunity stages:
Qualification
Proposal
Negotiation
Won
Lost

It also refers to opportunity status and open/won/lost states.
Decision
Stage and Status are separate concepts.
Stage
Represents sales progression:
Qualification
Proposal
Negotiation
Won
Lost

Status
Represents current state:
Open
Won
Lost

An active opportunity is:
Status = Open

When won:
Stage = Won
Status = Won

When lost:
Stage = Lost
Status = Lost

12. Opportunity ClosedDate
Requirement
The dashboard and reports require analysis of:
- Won opportunities
- Lost opportunities
- Monthly sales
Decision
Opportunity includes:
ClosedDate

This allows the system to distinguish:
CreatedDate

from:
ClosedDate

Monthly sales and won/lost reporting should use ClosedDate.
13. ModifiedDate
The mandatory entity definitions do not consistently list modification timestamps.
However, the assignment requires modification and auditability.
Decision
The main CRM entities include:
ModifiedDate

This applies to:
Customer
Lead
Opportunity
FollowUp
Activity
User

where appropriate.
14. Audit Log Structure
The assignment requires audit fields including:
- User
- Timestamp
- Action
- Module
- Record ID
- Result
- Metadata
The database entity additionally specifies:
OldValue
NewValue
IpAddress

Decision
AuditLog contains:
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

OldValue and NewValue may be stored as PostgreSQL JSONB.
Sensitive information must never be recorded.
15. Audit Sensitive Data Rule
Audit logs must never contain:
Passwords
Password hashes
Session cookies
Session tokens
API tokens
API secrets
Database credentials
Other authentication secrets

If metadata contains potentially sensitive information, it must be sanitized before insertion.
16. Audit Append-Oriented Design
Audit records are intended to be historical records.
Normal users must not be able to:
UPDATE audit records
DELETE audit records

The database role used for audit storage should restrict modification of existing audit records.
Audit records should therefore be treated as append-oriented.
17. Audit Transaction Decision
For a normal successful business operation:
Business change
+
Audit record

must be committed together.
Example:
Create Customer
     ↓
Insert Customer
     ↓
Insert Audit
     ↓
Commit

If the business operation fails:
Rollback

must remove the incomplete business change.
18. Failed Login Audit
Failed login attempts occur before a normal business transaction exists.
Therefore failed-login auditing may use a separate transaction.
Example:
Login attempt
   ↓
Password failure
   ↓
Update failed attempts
   ↓
Insert audit
   ↓
Commit

This ensures security events remain auditable.
19. Rejected Request Audit
Some rejected security/business operations may also be audited separately from the main business transaction.
Examples:
Unauthorized update
Failed security operation
Invalid login
Blocked account

The audit must never expose secrets.
20. Ownership Enforcement
Ownership must be enforced at the server/database query level.
The system must not:
Fetch every record
↓
Filter records in Python

when authorization can be enforced directly in SQL.
Example:
SELECT *
FROM opportunities
WHERE assigned_to = %s;

The current user's authorized scope must be passed into repository queries.
21. Current Role Must Come From Database
The role stored in the session must never be the only source of authorization.
For protected requests:
Session identity
      ↓
Load user from database
      ↓
Check active status
      ↓
Read current role
      ↓
Authorize

This prevents stale session roles from granting access after an administrator changes the user's role.
22. Registration Role
Self-registration must always assign:
Sales Executive

A public registration form must not allow a user to select:
Admin
Manager

Administrative roles can only be assigned by authorized administrators.
23. Generic Login Error
The application must not reveal whether a username/email exists.
Use a generic error:
Invalid credentials

for failed login attempts.
Avoid messages such as:
User does not exist
Wrong password
Account email not found

24. Session Reset on Login
Before creating authenticated session state:
session.clear()


must be performed.
The session should then contain only the minimum required authentication state.
Passwords and secrets must never be stored in the session.
25. Password Security Decision
Passwords are stored only as secure password hashes.
The implementation will use Werkzeug password hashing.
The project will not implement a custom password hashing algorithm.
The project will not create a separate plaintext/custom password table.
26. Password Policy
The password policy must be centralized and configurable.
At minimum:
Minimum password length
Non-empty password
Secure password validation

The exact policy should not be duplicated across routes.
27. Lockout Decision
The user table supports:
FailedLoginAttempts
LockoutUntil

The threshold and duration must be configurable.
Successful login resets the failed-attempt counter.
Administrators can unlock an account.
Lockout and unlock operations must be audited.
28. Timezone Decision
All business rules involving dates such as:
today
this week
this month
past date
upcoming date

must use:
Asia/Kolkata

timezone.
This is especially important for:
- Follow-up date validation
- Opportunity close-date validation
- Dashboard filters
- Monthly reporting
- Audit timestamps where business-local interpretation is required
29. Money Representation
All monetary values must use:
PostgreSQL NUMERIC(14,2)

and:
Python Decimal

Do not use floating-point arithmetic for money.
30. Active Opportunity Rule
An active opportunity must satisfy:
Status = Open
Amount > 0
Probability >= 0
Probability <= 100
ExpectedCloseDate is not in the past

The database may enforce static numeric constraints.
The service layer must enforce rules involving current date and business state.
31. Database Amount Constraint
The database amount field may allow:
Amount >= 0

because database constraints and service-level business rules serve different purposes.
The service must enforce:
Active opportunity amount > 0

This permits safe database representation while enforcing the actual business rule at the application layer.
32. Probability Rule
Probability must always satisfy:
0 <= Probability <= 100

The rule must be enforced:
Client side
Server side
Database where practical

Server-side validation is authoritative.
33. Follow-Up Date Rule
A follow-up date cannot be before the current business date.
Current business date is calculated using:
Asia/Kolkata

timezone.
This rule must be enforced on the server even if client-side date controls prevent invalid input.
34. Dashboard Pipeline Definition
The dashboard's:
Total Pipeline Value

means:
SUM(amount)

for:
Status = Open

Only active opportunities are included.
35. Weighted Pipeline Definition
Weighted pipeline is separate from Total Pipeline Value.
Formula:
Weighted Value = Amount × Probability / 100

Weighted pipeline belongs primarily in the Pipeline Report.
The dashboard's standard Total Pipeline Value should not silently become weighted pipeline.
36. Dashboard Date Semantics
Different dashboard metrics use different date fields.
Customers
→ CreatedDate

Leads
→ CreatedDate

Opportunities
→ CreatedDate

Won Opportunities
→ ClosedDate

Lost Opportunities
→ ClosedDate

Monthly Sales
→ ClosedDate

Follow-Ups
→ FollowUpDate

Activities
→ ActivityDate

This prevents incorrect reporting based on a single universal date field.
37. Dashboard Role Scope
Admin
Organization-wide view.
Manager
Manager/team CRM scope.
Sales Executive
Assigned/personal CRM scope.
Dashboard aggregation queries must enforce the same authorization model as normal CRM pages.
38. Lead Conversion Transaction
Lead conversion is treated as one business transaction.
Possible sequence:
Validate lead
↓
Check valid status
↓
Find or create customer
↓
Create opportunity if required
↓
Update lead to Converted
↓
Create audit records
↓
Commit

If any required operation fails:
Rollback everything

No partial conversion is allowed.
39. Duplicate Customer During Conversion
If an existing customer can be safely identified using available identity information, the lead may be linked to that customer.
If identity cannot be established safely:
Reject conversion

rather than silently merging unrelated customers.
If the evaluator specifies a different duplicate-handling rule, update this note before implementation changes.
40. Customer Contact Reuse
Inactive customer records remain part of the CRM history.
Therefore their email/phone identity should not automatically become available for reuse.
This avoids creating duplicate identities by deactivating an old customer and recreating the same person as a new customer.
41. API DTO Decision
Database entities must not be returned directly as API responses.
API responses must use explicit DTO/serializer functions.
Reasons:
- Prevent accidental sensitive-field exposure.
- Separate database structure from API contract.
- Make API behavior easier to explain.
- Keep API responses stable.
42. API Status Codes
The implementation should use:
200 OK
201 Created
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict

according to the situation.
Examples:
Invalid data
→ 400

Not authenticated
→ 401

Authenticated but not allowed
→ 403

Record not found
→ 404

Duplicate/conflict
→ 409

43. API Authentication Decision
All protected API endpoints require authentication.
API authorization is separate from merely proving identity.
For example:
Authenticated Sales Executive

does not automatically mean:
Can access every customer.

Ownership and role scope remain enforced.
44. Client vs Server Validation
Client-side validation exists for usability.
Server-side validation exists for correctness and security.
Therefore:
Client validation

must never be considered sufficient.
An attacker may bypass JavaScript.
Every important rule must be enforced again on the server.
45. Business Rules Location
Business rules belong primarily in:
validation/business_rules.py

or the appropriate service when the rule requires workflow context.
Examples:
Probability 0–100
Amount > 0
Past close date
Past follow-up date
Lead transition
Ownership
Duplicate detection

46. Enum/Status Single Source of Truth
Status, stage and type values must not be independently redefined in multiple places.
Where practical, values should be centralized and reused by:
Python
SQL
JavaScript
Templates
Validation

Examples:
Lead statuses
Opportunity stages
Opportunity statuses
Follow-up statuses

This reduces spelling mismatches and invalid states.
47. SQL Location Rule
All application SQL must live inside:
repositories/

SQL must not be written directly in:
routes/
services/
templates/
static/

except for clearly documented schema/seed SQL under:
sql/

48. Transaction Location Rule
Services own business transactions.
Repositories perform database operations but do not independently decide the complete business transaction.
This makes workflows such as lead conversion understandable.
49. Manager Visibility Implementation
Manager visibility should be centralized rather than duplicated.
Conceptually:
visible_user_ids(current_user)

returns the users/owners whose records the manager may access.
Repositories use that scope in SQL.
If the organization later introduces explicit teams, the implementation can be extended without redesigning every module.
50. Error Handling Decision
The application should provide centralized handlers for:
400
403
404
500

User-facing pages should show friendly messages.
Debug stack traces must not be shown in production-like behavior.
51. No Sensitive Data in Logs
Application logs must not contain:
Passwords
Password hashes
Tokens
Session cookies
API secrets
Database credentials

Debugging information must be sanitized.
52. No Sensitive Data in API
API responses must not expose:
PasswordHash
Password
Session data
Authentication secrets
Database configuration
Internal stack traces

53. No Sensitive Data in Audit
Audit metadata must also exclude:
Passwords
Password hashes
Tokens
Secrets

Audit logging must never become a mechanism for accidentally storing credentials.
54. Database Security
The application database user should have only the permissions necessary for the application.
Audit data should be protected against normal UPDATE/DELETE operations.
Database credentials must be supplied through environment configuration.
55. Rate Limiting
Flask-Limiter is included in the stack.
Rate limiting should be used where it provides clear security value, especially authentication-sensitive endpoints.
Do not add unnecessary rate limits that interfere with normal development or testing.
56. CSRF Decision
Browser state-changing requests use Flask-WTF CSRF protection.
The application must not disable CSRF globally merely because an individual form is inconvenient.
API behavior must be designed separately from browser form CSRF.
57. REST API and Browser Sessions
The web application and API are conceptually separate interfaces.
The API must enforce authentication and authorization explicitly.
Do not accidentally create an API endpoint that becomes publicly accessible simply because its browser page is protected.
58. Testing Decision
Every implemented feature must have corresponding tests.
A phase is not considered complete merely because the application starts.
Tests must verify:
Expected behavior
Invalid behavior
Authorization
Business rules
Security where relevant

59. Test Database
Tests should use a controlled test database/configuration.
Tests must not depend on arbitrary production/development data.
Seed/test fixtures should be deterministic.
60. Test Isolation
Tests should avoid depending on execution order.
Each test should create or reset the state it requires.
61. Documentation Decision
The project documentation consists of:
README.md
API.md
MASTER_BLUEPRINT.md
SPECIFICATION_NOTES.md

These files must remain consistent with the actual implementation.
Do not document an endpoint or feature that does not exist.
62. README Scope
README should document:
- Project purpose
- Technology stack
- Installation
- PostgreSQL setup
- Environment configuration
- Database initialization
- Seed data
- Running the application
- Running tests
- Demo users
- Architecture overview
63. API Documentation Scope
API.md must document only implemented endpoints.
For every endpoint, document:
HTTP method
URL
Authentication requirement
Authorization requirement
Request parameters
Request body
Response
Possible status codes
Example usage

64. Explicit Non-Scope
The following are not part of the project unless explicitly approved later:
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
JWT
Microservices
AI
LLM
Chatbot
Vector database
Payment processing
SMS automation
Email automation
Mobile application
Desktop application
Blockchain

The project must not grow into an unrelated enterprise platform.
65. No Silent Technology Additions
If implementation appears easier with another library or technology:
STOP

Do not install it automatically.
Ask for approval first.
66. No Silent Architecture Changes
If an implementation problem suggests changing:
routes
services
repositories
schemas
security
validation

architecture, do not silently restructure the project.
Explain the problem and request approval.
67. No Silent Requirement Changes
If the assignment appears inconsistent:
Do not silently choose one interpretation.

Record the issue here and ask for clarification where necessary.
68. Phase-Based Implementation Rule
Development must happen in the following order:
Phase 0
↓
Phase 1
↓
Phase 2
↓
Phase 3
↓
Phase 4
↓
Phase 5
↓
Phase 6
↓
Phase 7
↓
Phase 8
↓
Phase 9
↓
Phase 10
↓
Phase 11
↓
Phase 12
↓
Phase 13
↓
Phase 14

Do not jump ahead unless explicitly requested.
69. Phase 0 Decision
Phase 0 must establish:
- Project structure
- Configuration
- Application factory
- Database foundation
- Extensions
- Testing foundation
- Documentation foundation
Phase 0 must not implement complete CRM functionality.
70. Phase 1 Decision
Phase 1 establishes the PostgreSQL database schema, constraints, indexes and seed data.
Authentication and CRM workflows are not implemented here.
71. Phase 2 Decision
Phase 2 establishes authentication and account security.
It must include:
Registration
Login
Logout
Password hashing
Password policy
Failed attempts
Lockout
Session security

72. Phase 3 Decision
Phase 3 establishes:
RBAC
Authorization
Ownership foundation
Audit infrastructure

Audit is intentionally implemented before the CRM modules so that later modules can audit actions as they are built.
73. Phase 4 Decision
Phase 4 establishes the common application UI and error handling.
This includes:
base.html
Navigation
Flash messages
Error pages
Common CSS

74. Phase 5 Decision
Phase 5 implements Customer Management.
Customer creation, modification, assignment and relevant state changes must be audited immediately.
Do not postpone audit implementation until the end.
75. Phase 6 Decision
Phase 6 implements Lead Management and conversion.
Lead transitions must use the approved transition matrix.
Lead conversion must be transactional.
76. Phase 7 Decision
Phase 7 implements Opportunity Management and pipeline logic.
The distinction between:
Stage
Status

must remain intact.
77. Phase 8 Decision
Phase 8 implements:
Follow-ups
Activities

Date and ownership rules must be enforced server-side.
78. Phase 9 Decision
Phase 9 implements administrative user/role functionality.
Only Admin can perform unrestricted security administration.
79. Phase 10 Decision
Phase 10 implements:
Dashboard
KPIs
Role scope
Date filters
Chart.js

Dashboard queries must be server-authorized.
80. Phase 11 Decision
Phase 11 implements the required reports.
Reporting logic must respect the same authorization scope as the CRM modules.
81. Phase 12 Decision
Phase 12 implements the REST API.
API security, validation, DTOs and status codes must be included.
82. Phase 13 Decision
Phase 13 is for:
Integration
Security testing
Regression testing

No major new functionality should be introduced here unless a defect requires it.
83. Phase 14 Decision
Phase 14 is final acceptance testing and demonstration preparation.
The acceptance scenarios in MASTER_BLUEPRINT.md must be executed.
84. Open Question — Flask Acceptance
The assignment contains ASP.NET-specific implementation requirements.
Before final submission, clarify whether:
Flask + PostgreSQL

is accepted as an equivalent implementation.
If the evaluator requires ASP.NET specifically, the implementation technology may need to change.
Until such clarification is received, the project follows the approved Flask stack.
85. Open Question — Manager Team Definition
The assignment refers to manager/team scope but does not define a dedicated team structure.
Current implementation:
Manager visibility is centralized through visible_user_ids().

If the evaluator defines a specific team model, update this note and the blueprint before implementation changes.
86. Open Question — Lead Conversion Duplicate Handling
The assignment requires lead conversion but does not fully define what should happen when the customer already exists.
Current decision:
Safely identifiable existing customer
→ link

Ambiguous duplicate
→ reject and ask user to resolve

Do not silently merge customers.
87. Open Question — API Authentication Mechanism
The assignment requires secure authenticated APIs but does not mandate JWT specifically.
Current project deliberately does not add JWT.
The API authentication mechanism must remain consistent with the fixed stack and evaluator expectations.
Do not introduce JWT without explicit approval.
88. Open Question — Export Format
Reports mention export where implemented, but the exact export format is not the central requirement.
Do not add a complex export subsystem without approval.
If export is implemented, document the format in:
API.md
README.md

or the relevant report documentation.
89. Decision Priority
When requirements appear to conflict, use this priority:
1. Explicit assignment functional requirement
2. Explicit assignment security requirement
3. Approved clarification from evaluator
4. MASTER_BLUEPRINT.md
5. SPECIFICATION_NOTES.md decisions
6. Implementation convenience

Implementation convenience must never override a functional or security requirement.
90. Change Control
Any major change to the project must answer:
What requirement caused the change?
Why is the current implementation insufficient?
What files are affected?
What tests must change?
Does the change affect the architecture?
Does the change affect security?

Only after review should the change be implemented.
91. Final Design Principle
AcxiomCRM is intentionally designed as a:
Student-friendly
Layered
Secure
Role-based
Database-backed
Tested
Explainable
CRM

The goal is not maximum technical complexity.
The goal is correct implementation of the required assignment.
92. Final Rule
When in doubt:
STOP
READ MASTER_BLUEPRINT.md
READ SPECIFICATION_NOTES.md
CHECK THE ASSIGNMENT
ASK BEFORE CHANGING THE DESIGN

Never silently invent requirements.
Never silently remove requirements.
Never silently add technologies.
Never silently weaken security.
The blueprint and these specification notes must remain the project's implementation contract.

93. Phase 5 Customer Management Decisions (Approved)
1. CustomerCode Generation:
   Automatically generated by the system sequentially in customer_service (e.g. CUST-005 based on next sequence/count) to guarantee uniqueness and consistency with seed data.
2. Phone Validation:
   Validated server-side: 10 to 15 digits, allowing optional leading '+' and hyphens/spaces (e.g. regex r"^\+?[0-9\s\-]{10,20}$" with 10-15 digits total, matching seed format '+91-9876543210').
3. Sales Executive Creation Ownership:
   When a Sales Executive creates a customer, the customer is automatically self-assigned (assigned_to = current_user['user_id']). Sales Executives cannot assign customers to other users. Admins and Managers can choose any active Sales Executive.
4. Customer Deactivation and Status Changes:
   Restricted to Admin and Manager roles. Sales Executives are not permitted to deactivate or change the status of customers; attempts are rejected with HTTP 403 Forbidden.

94. Phase 6 Lead Management & Conversion Decisions (Approved)
1. LeadCode:
   Automatically generated sequentially in the format LEAD-001, LEAD-002, LEAD-003, ... based on next lead_id. Users do not manually enter LeadCode.
2. Lead Creation Ownership:
   - Sales Executive: Lead is automatically assigned to the authenticated Sales Executive. Submitted assigned_to is ignored/rejected.
   - Admin/Manager: May select an active Sales Executive as AssignedTo. Unassigned leads are not permitted.
3. Conversion Eligibility & Authorization:
   - Only Qualified Leads may be converted (Qualified -> Converted). All other transitions to Converted (New, Contacted, Unqualified, Lost, Converted) are rejected.
   - Admin and Manager may convert Leads within their visibility scope.
   - Sales Executives may convert only Qualified Leads assigned to themselves. Unauthorized conversion returns 403 Forbidden.
4. Conversion Workflow:
   - Uses a dedicated confirmation/form flow (/leads/<id>/convert).
   - Identifies/links an existing Customer or creates a new Customer.
   - Optionally creates an Opportunity if requested by user.
   - Executes in ONE atomic PostgreSQL transaction: Customer create/link, Opportunity create (if requested), Lead status -> Converted, and audit events. Full rollback on any failure.
5. Existing Customer Matching:
   - Email-only unique match: link existing Customer.
   - Phone-only unique match: link existing Customer.
   - Email and phone both match the same Customer: link existing Customer.
   - Email identifies Customer A while phone identifies Customer B: reject as ambiguous duplicate.
   - No matching Customer: create new Customer.
   - Never silently merge Customers.
6. Customer Mapping:
   - LeadName -> CustomerName, CompanyName -> CompanyName, Email -> Email, Phone -> Phone, AssignedTo -> AssignedTo, Current authenticated user -> CreatedBy, Status -> Active.
   - Address/City/State: supplied via conversion form.
   - CustomerCode: generated sequentially using existing CustomerCode mechanism.
7. Opportunity Mapping (if Create Opportunity selected):
   - OpportunityName: supplied via conversion form.
   - CustomerId: created or linked Customer ID.
   - LeadId: original Lead ID.
   - Amount: initially populated from Lead.ExpectedValue (editable in form, validated >= 0).
   - ExpectedCloseDate: required conversion form input.
   - Stage: 'Qualification', Status: 'Open', AssignedTo: Lead.AssignedTo.
   - Probability: supplied/confirmed through conversion form, validated 0–100.
8. Conversion Auditing:
   - Customer CREATE (or linkage audit if linked).
   - Opportunity CREATE if created.
   - Lead STATUS_CHANGE: Qualified -> Converted.
   - All audit logs and data mutations commit together in the same transaction.
9. Security:
   - Full server-side authorization check. Do not trust hidden or submitted form roles/status.
10. Concurrency:
   - Row-level locking (SELECT ... FOR UPDATE) on the Lead row inside the transaction prevents concurrent double-conversion.
11. Lead Status Transition Matrix:
   - New -> Contacted, Unqualified, Lost
   - Contacted -> Qualified, Unqualified, Lost
   - Qualified -> Converted, Lost
   - Unqualified -> terminal (no transitions permitted)
   - Converted -> terminal (no transitions permitted)
   - Lost -> terminal (no transitions permitted)

95. Phase 7 Opportunity Management Decisions (Approved)
1. Stage Transition Matrix:
   - Linear progression with drop to Lost:
     * Qualification -> Proposal, Lost
     * Proposal -> Negotiation, Lost
     * Negotiation -> Won, Lost
     * Won -> terminal (no transitions permitted)
     * Lost -> terminal (no transitions permitted)
2. Inactive Customer Policy:
   - Only Active customers can receive new Opportunities. Inactive customers are rejected with 400 Bad Request.
3. Opportunity Creation Ownership:
   - Sales Executive: Opportunity is automatically self-assigned (assigned_to = current_user['user_id']). Any submitted assigned_to is ignored/overwritten.
   - Admin/Manager: May assign any active Sales Executive (role_id = 3, is_active = True).
4. Terminal Status & Reopening:
   - Won and Lost opportunities are strictly terminal. They cannot be reopened or transitioned to any other stage/status.
5. Database Schema & Fields:
   - Opportunities table adheres strictly to Phase 1 PostgreSQL schema: opportunity_id, opportunity_name, customer_id, lead_id, amount, stage, probability, expected_close_date, status, created_date, modified_date, closed_date, assigned_to.
   - No columns for source or notes exist in the schema; therefore, no source or notes fields are stored or required.
6. Stage and Status Consistency:
   - Active stages (Qualification, Proposal, Negotiation): status = 'Open', closed_date = NULL.
   - Stage 'Won': status = 'Won', closed_date = CURRENT_TIMESTAMP.
   - Stage 'Lost': status = 'Lost', closed_date = CURRENT_TIMESTAMP.
   - Inconsistent combinations (e.g. Won with Open, Proposal with Won) are rejected.
7. Active Opportunity Rules:
   - Status = Open
   - Amount > 0 (NUMERIC(14,2) in PostgreSQL, Decimal in Python; floats strictly prohibited)
   - Probability: integer 0–100 inclusive
   - ExpectedCloseDate: must be today or in the future in Asia/Kolkata timezone
8. Lead Relationship:
   - In manual creation: lead_id is optional (NULL).
   - In Lead conversion: lead_id is linked to the converted lead.
9. Pipeline Calculations:
   - Total Pipeline Value = SUM(amount) for Open opportunities only (Decimal).
   - Weighted Pipeline Value = SUM(amount * probability / 100) for Open opportunities only (Decimal).
   - Closed opportunities (Won, Lost) are strictly excluded from active pipeline values.
   - Calculations are SQL/service scoped by ownership (Sales Exec sees only own pipeline; Admin/Manager see scope).
10. Auditing:
   - Every creation (CREATE), edit (UPDATE), stage/status change (STATUS_CHANGE) is audited atomically within the same PostgreSQL transaction.

96. Phase 7 Opportunity Creation Assignment Clarification (Approved)
1. Opportunity Creation Ownership Rules:
   - Sales Executive creates an Opportunity:
     * Automatically self-assigns to the authenticated Sales Executive (assigned_to = current_user['user_id']).
     * Any submitted assigned_to value is ignored/overwritten.
   - Admin/Manager creates an Opportunity:
     * Must explicitly select an active Sales Executive (role_id = 3, is_active = True).
     * Missing or empty assigned_to value is strictly rejected with 400 Bad Request ("An active Sales Executive must be explicitly selected.").
     * Silent defaulting or fallback to the Customer's assigned Sales Executive is prohibited.
```