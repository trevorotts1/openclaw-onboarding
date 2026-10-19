/* Seat data for the nine elders. Text is copied from each shipped pack
 * (advisors/<seat>/profile.json); tests/chamber-seats.test.ts guards drift.
 * `pill` (optional) is the name pill text when it differs from `name`.
 * `weighing` is a short paraphrase of the pack's owned question. */
(function (root) {
  var ns = root.councilChamber = root.councilChamber || {};

  var SEATS = [
    {
      id: "simon-sinek", name: "Simon Sinek", short: "Sinek",
      domain: "purpose and strategic alignment",
      owns: "Does this decision express why the business exists, and are the proposed actions consistent with that purpose?",
      weighing: "does this express why the business exists, and do the actions fit that purpose?",
      sources: ["Start with Why", "Find Your Why"]
    },
    {
      id: "td-jakes", name: "T. D. Jakes", short: "Jakes",
      domain: "instinct, reinvention, and communication",
      owns: "What opportunity or capacity is the client sensing, what established assumption needs challenging, and how can the vision be communicated effectively?",
      weighing: "what is the client sensing, what assumption needs challenging, and can the vision be told?",
      sources: ["Instinct", "Disruptive Thinking", "Don't Drop the Mic"]
    },
    {
      id: "oprah-winfrey", name: "Oprah Winfrey", short: "Oprah",
      domain: "intention, significance, and human connection",
      owns: "What is the real intention behind this choice, and how does it affect the people it is supposed to serve?",
      weighing: "what is the real intention behind this choice, and how does it affect the people served?",
      sources: ["The Path Made Clear", "Verified first-person interviews and reflections", "What I Know For Sure"]
    },
    {
      id: "tiffany-aliche", name: "Tiffany Aliche", short: "Aliche",
      domain: "financial stability and sustainable commitments",
      owns: "Can the client make this commitment without destabilizing the foundation that supports their life and business?",
      weighing: "can this commitment be made without destabilizing the foundation under life and business?",
      sources: ["Get Good with Money", "Documented financial-wholeness teaching"]
    },
    {
      id: "russell-brunson", name: "Russell Brunson", short: "Brunson",
      domain: "offers, acquisition, and conversion",
      owns: "Who wants this, how will they find it, and what credible path turns interest into a purchase?",
      weighing: "who wants this, how will they find it, and what path turns interest into a purchase?",
      sources: ["DotCom Secrets", "Expert Secrets", "Network Marketing Secrets - The Hidden Funnel Strategy", "The Marketing Secrets Blackbook", "Lead Funnels", "Traffic Secrets", "The Funnel Hacker's Cookbook"]
    },
    {
      id: "michelle-obama", name: "Michelle Obama", short: "Obama",
      domain: "grounded leadership, identity, and community",
      owns: "How can the client move forward with confidence and integrity while considering the people affected?",
      weighing: "how can the client move forward with confidence and integrity, given the people affected?",
      sources: ["Becoming", "The Light We Carry"]
    },
    {
      id: "brene-brown", name: "Brené Brown", short: "Brené Brown",
      domain: "courage, trust, and accountable behavior",
      owns: "What difficult conversation or vulnerable action is being avoided, and what would trustworthy leadership require?",
      weighing: "what hard conversation is being avoided, and what would trustworthy leadership require?",
      sources: ["Dare to Lead", "Documented BRAVING material", "Atlas of the Heart"]
    },
    {
      id: "dennis-kimbro", name: "Dr. Dennis Kimbro", pill: "Dennis Kimbro", short: "Kimbro",
      domain: "ownership, wealth creation, and achievement",
      owns: "Does the decision build enduring capability, ownership, and wealth, or merely create more activity?",
      weighing: "does this build lasting capability, ownership and wealth, or just more activity?",
      sources: ["Think and Grow Rich: A Black Choice", "The Wealth Choice", "What Makes the Great Great"]
    },
    {
      id: "les-brown", name: "Les Brown", short: "Les Brown",
      domain: "self-belief, resilience, and committed action",
      owns: "Is the obstacle a real constraint, a skill gap, or a limiting belief, and what meaningful action comes next?",
      weighing: "is the obstacle a constraint, a skill gap or a limiting belief, and what action is next?",
      sources: ["It's Not Over Until You Win", "Verified public teaching", "Live Your Dreams"]
    }
  ];

  var byId = {};
  var order = [];
  SEATS.forEach(function (s) {
    s.disclaimer = "A simulated advisor built from " + s.name + "'s public work (" +
      s.sources.join(", ") + "). Not the person.";
    byId[s.id] = s;
    order.push(s.id);
  });

  function get(id) {
    var s = byId[id];
    if (s) return s;
    return { id: String(id), name: String(id), short: String(id), domain: "", owns: "", weighing: "", sources: [], disclaimer: "" };
  }

  function portraitSources(id) {
    return ["portraits/" + id + ".webp", "portraits/" + id + ".svg"];
  }

  ns.seats = { order: order, get: get, portraitSources: portraitSources };
})(typeof globalThis !== "undefined" ? globalThis : this);
