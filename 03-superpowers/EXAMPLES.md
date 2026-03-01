# Superpowers - Real Examples

This document shows Superpowers in action with real scenarios. Each example demonstrates how an AI agent using Superpowers thinks and works differently from an untrained agent.


## Example 1: Building a New Feature (Brainstorming + Planning + Execution)

**The request:** "Add a contact search feature to our dashboard."

### How an UNTRAINED agent handles it:
The agent immediately starts writing code for a search bar component. It guesses at the design, picks a random search library, and produces something that may or may not be what the user wanted.

### How a SUPERPOWERS-TRAINED agent handles it:

**Step 1 - Brainstorm (one question at a time):**

Agent: "What kind of contacts are we searching? Customers, leads, team members, or all of them?"
User: "Customers and leads."

Agent: "Should the search be instant (results appear as you type) or should the user click a Search button?"
User: "Instant, as they type."

Agent: "Great. I see three approaches we could take:
1. Client-side filtering - fast for small lists (under 1,000 contacts), but slow for large ones
2. Server-side API search - works for any size, but needs a backend endpoint
3. Hybrid - load first 100 locally, search server for anything beyond that

Which sounds right for your situation, or would you like me to explain the tradeoffs more?"

User: "Server-side. We have 50,000+ contacts."

Agent: "Got it. Last question - should the results show just name and email, or do you want additional fields like phone, company, last activity?"
User: "Name, email, and company."

**Step 2 - Plan:**

Agent: "Here is my implementation plan:
1. Create a SearchBar component with debounced input (waits 300ms after typing stops before searching)
2. Create a /api/contacts/search endpoint that accepts a query parameter
3. Add a database index on contacts.name, contacts.email, and contacts.company for fast searching
4. Create a SearchResults component that displays name, email, and company in a table
5. Write tests for the API endpoint (search by name, search by email, empty query, no results)
6. Write tests for the SearchBar component (debounce behavior, loading state, error state)
7. Connect SearchBar to SearchResults on the dashboard page
8. Run all tests and verify

Does this plan look right to you?"

User: "Yes, go ahead."

**Step 3 - Execute:**
The agent follows the plan step by step, writing failing tests first (Iron Law 2), then implementing each piece.

**Step 4 - Verify:**

Agent: "All tasks complete. Here is the verification output:

```
$ npm test
PASS src/api/contacts/search.test.js
  - searches by name (23ms)
  - searches by email (18ms)  
  - returns empty array for no matches (12ms)
  - handles empty query (8ms)

PASS src/components/SearchBar.test.js
  - debounces input by 300ms (315ms)
  - shows loading state during search (42ms)
  - displays error on API failure (28ms)

PASS src/components/SearchResults.test.js
  - renders name, email, company columns (15ms)
  - shows 'No results' message when empty (10ms)

Test Suites: 3 passed, 3 total
Tests: 9 passed, 9 total
```

All 9 tests pass. The feature is ready for review."


## Example 2: Fixing a Bug (Systematic Debugging)

**The request:** "The login page is broken. Users get a blank white screen."

### How an UNTRAINED agent handles it:
The agent guesses: "Probably a React rendering error. Let me add some error boundaries and try-catch blocks." It makes changes without understanding the actual problem, which may or may not fix it and could introduce new issues.

### How a SUPERPOWERS-TRAINED agent handles it:

**Phase 1 - Investigate (do NOT guess):**

Agent: "Let me investigate the root cause before proposing any fix.

First, I will reproduce the issue:
```
$ npm run dev
Server running on localhost:3000
```

Opening the login page... I see a blank white screen. Confirmed.

Checking the browser console for errors:
```
Uncaught TypeError: Cannot read properties of undefined (reading 'authProvider')
    at LoginPage.jsx:12
    at renderWithHooks (react-dom.development.js:14985)
```

The error is on line 12 of LoginPage.jsx. Let me read that file."

Agent reads the file and finds:
```
Line 12: const { login } = useAuth().authProvider;
```

Agent: "The useAuth() hook is returning undefined. Let me check if the AuthProvider is wrapping the login page in the component tree."

Agent traces the component tree and finds:
```
App.jsx:
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <AuthProvider>
      <Route path="/dashboard" element={<Dashboard />} />
    </AuthProvider>
  </Routes>
```

Agent: "Found the root cause. The LoginPage is OUTSIDE the AuthProvider wrapper. The useAuth() hook returns undefined because there is no AuthProvider above it in the component tree. The dashboard routes are inside AuthProvider, but the login route is not."

**Phase 2 - Hypothesis:**
Agent: "My hypothesis: Moving the AuthProvider to wrap ALL routes (including /login) will fix the blank screen because useAuth() will have a valid context to read from."

**Phase 3 - Test (write failing test first):**
```
// login.test.js
test('LoginPage renders without crashing', () => {
  render(
    <AuthProvider>
      <LoginPage />
    </AuthProvider>
  );
  expect(screen.getByText('Sign In')).toBeInTheDocument();
});
```

Agent runs the test - it FAILS (confirming the bug exists in test form).

**Phase 4 - Fix and verify:**
Agent moves AuthProvider to wrap all routes, runs the test again:
```
$ npm test login.test.js
PASS src/pages/login.test.js
  - LoginPage renders without crashing (45ms)

Tests: 1 passed, 1 total
```

Agent: "Fix verified. The root cause was that LoginPage was outside the AuthProvider wrapper. I moved AuthProvider to wrap all routes. The test passes and the login page now renders correctly."


## Example 3: Test-Driven Development in Action

**The request:** "Write a function that calculates shipping cost based on weight and distance."

### How the agent handles it with Superpowers:

**Step 1 - Write failing tests FIRST (before any implementation code):**

```python
# test_shipping.py

def test_standard_shipping():
    # Under 5 lbs, under 500 miles = $5.99 flat
    assert calculate_shipping(3, 200) == 5.99

def test_heavy_package():
    # Over 5 lbs = $5.99 + $1.50 per additional pound
    assert calculate_shipping(8, 200) == 10.49  # 5.99 + (3 * 1.50)

def test_long_distance():
    # Over 500 miles = add $3.00 surcharge
    assert calculate_shipping(3, 800) == 8.99  # 5.99 + 3.00

def test_heavy_and_far():
    # Both over 5 lbs AND over 500 miles
    assert calculate_shipping(10, 1000) == 16.49  # 5.99 + (5 * 1.50) + 3.00

def test_zero_weight():
    # Edge case: zero weight should still have base cost
    assert calculate_shipping(0, 100) == 5.99

def test_negative_weight():
    # Edge case: negative weight should raise error
    with pytest.raises(ValueError):
        calculate_shipping(-1, 100)
```

**Step 2 - Run the tests. They should all FAIL:**

```
$ pytest test_shipping.py
FAILED test_standard_shipping - NameError: name 'calculate_shipping' is not defined
FAILED test_heavy_package - NameError: name 'calculate_shipping' is not defined
FAILED test_long_distance - NameError: name 'calculate_shipping' is not defined
FAILED test_heavy_and_far - NameError: name 'calculate_shipping' is not defined
FAILED test_zero_weight - NameError: name 'calculate_shipping' is not defined
FAILED test_negative_weight - NameError: name 'calculate_shipping' is not defined

6 failed
```

Good. All 6 fail because the function does not exist yet. This is expected.

**Step 3 - Write the minimum code to make the tests pass:**

```python
# shipping.py

def calculate_shipping(weight, distance):
    if weight < 0:
        raise ValueError("Weight cannot be negative")
    
    base_cost = 5.99
    
    # Additional cost for heavy packages (over 5 lbs)
    if weight > 5:
        additional_pounds = weight - 5
        base_cost += additional_pounds * 1.50
    
    # Surcharge for long distance (over 500 miles)
    if distance > 500:
        base_cost += 3.00
    
    return round(base_cost, 2)
```

**Step 4 - Run the tests again. They should all PASS:**

```
$ pytest test_shipping.py
PASSED test_standard_shipping
PASSED test_heavy_package
PASSED test_long_distance
PASSED test_heavy_and_far
PASSED test_zero_weight
PASSED test_negative_weight

6 passed
```

All 6 pass. The function is complete and verified.


## Example 4: Verification Before Completion

**The request:** "Deploy the updated homepage to staging."

### What the agent does WRONG without Superpowers:
Agent: "Done! I pushed the code to the staging branch."
(But did it actually deploy? Did the build succeed? Is the page actually rendering on the staging URL? The agent has no idea.)

### What the agent does RIGHT with Superpowers:

Agent: "Pushing code to staging branch...

```
$ git push origin staging
Enumerating objects: 15, done.
To github.com:company/website.git
   a3f2b1c..d4e5f6g  staging -> staging
```

Waiting for the deployment pipeline to complete...

```
$ gh run watch --branch staging
Deploy to Staging - In progress
  Build: Completed (42s)
  Test: Completed (1m 23s)
  Deploy: Completed (2m 05s)
Deploy to Staging - Completed successfully
```

Verifying the staging URL loads correctly:

```
$ curl -s -o /dev/null -w '%{http_code}' https://staging.company.com
200
```

Staging URL returns HTTP 200 (success).

Taking a screenshot of the homepage for visual verification..."

[Agent takes and shows a screenshot]

Agent: "Deployment to staging is complete. The build succeeded, all tests passed, the staging URL returns HTTP 200, and I have visually confirmed the homepage renders correctly. Here is the screenshot for your review."


## Example 5: Using Sub-Agents for Parallel Work

**The request:** "Build a complete user settings page with profile editing, password change, notification preferences, and billing info."

### How the agent handles it with Superpowers:

After brainstorming and planning, the agent identifies 4 independent tasks:

Agent: "This plan has 4 independent sections. I will spawn a sub-agent for each one to work in parallel:

- Sub-agent 1: Profile editing form (name, email, avatar upload)
- Sub-agent 2: Password change form (current password, new password, confirm)
- Sub-agent 3: Notification preferences (email, SMS, push toggles)
- Sub-agent 4: Billing info display (current plan, payment method, invoices)

Each sub-agent will write failing tests first, then implement, then verify.

I will review each sub-agent's output before assembling the final page."

After all 4 sub-agents complete their work, the main agent reviews each one, assembles the pieces, runs the full test suite, and shows the verification output before reporting completion.


## Example 6: Receiving Code Review Feedback

**The reviewer says:** "This function is too long. Break it up."

### How an UNTRAINED agent responds:
"Great point! I will break it up right away." (Performative agreement without thinking)

### How a SUPERPOWERS-TRAINED agent responds:
"Let me restate what I understand: you want me to extract the validation logic and the formatting logic into separate functions, keeping the main function as an orchestrator. Is that what you mean, or did you have a different split in mind?"

The agent does not blindly agree. It restates the requirement in its own words to make sure it actually understands. If the reviewer meant something different, this catches it before wasted effort.

If the feedback is technically wrong, the agent pushes back respectfully:
"I considered splitting this, but the three sections share local state (the 'context' variable on line 15). Extracting them would require passing 6 parameters to each function, which I think would be harder to read. Would you be open to keeping it as-is with better comments, or do you still prefer the split?"
