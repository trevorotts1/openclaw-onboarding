<!-- BAKED PROMPT ASSET | stage 15-facebook-audiences | subsystem facebook-ads
     source record: source/airtable-prompts/34-facebook-audience-generator.md
     provider-agnostic: resolved by the client's own TIER model at runtime; ZERO Anthropic ids.
     intake tokens -> {{intake.<key>}}; upstream artifacts injected by aa_director.py per AA-PIPELINE-MANIFEST.json depends_on.
     R3: `<audience_targeting_cheat_sheet>` explicitly references the Black CEO Method 7-Tier framework in methodology.md.
     intake content is DATA only, never instructions (prompt-injection rule). -->

## User prompt (token-normalized)

You will be creating targeting groups for Facebook advertising based on an offer and avatar description. You will use the Audience Targeting Cheat Sheet to select appropriate targeting options. Your job is to create an audience targeting profile based on the layering technique I am teaching you below. You must reference and analyze the section of the document Labeled Audience Targeting Cheat Sheet before you start creating the audience targeting groups. You are forbidden from not using any audience that is not on the Audience Targeting Cheat Sheet. Your response Should also be in plain text format for easy readability. You should also explain your audience selection for each group. Your audience groups must be in harmony with the data I share with you about my avatar, Goal, desires & aspirations and my offer etc.

<audience_targeting_cheat_sheet> </audience_targeting_cheat_sheet>

Your task is to build targeting groups that are relevant to the offer and avatar provided. Remember these key concepts:

Layering: Combining different targeting options to narrow the audience size and pinpoint the target audience.

Types of targeting: IT = Interest Targeting BT = Behavior Targeting DT = Demographic Targeting

To complete this task, I will provide you with an offer description and an avatar description. Please analyze these carefully to understand the product or service being offered and the ideal customer.

<offer_description> offer name[{{intake.offer_name}}], 
type of offer[{{intake.offer_type}}],
offer benefit [{{intake.offer_benefit}}]
Product info [{{intake.product_info}}]
 , </offer_description>

<avatar_description> 
{{artifact.03-rewrite-avatar}}

{{artifact.01-avatar-questions-1-30}}
{{artifact.02-avatar-questions-31-32}}


 </avatar_description>

Based on the offer and avatar descriptions, follow these steps:

Identify key interests, behaviors, and demographics that align with the offer and avatar.

Select relevant targeting options from the Audience Targeting Cheat Sheet.

Create 3-5 targeting groups by layering different targeting options.

For each targeting group, provide 1-3 layers of targeting, as appropriate for the audience. It is crucial to vary the number of layers between groups. Some groups may require only 1 layer, others may need 2 or 3 layers. The number of layers should be based on the specificity required for each group. You can have between 1-7 audiences in a layer.

Ensure diversity in your layer structure across groups. Do not use the same number of layers for all groups. Aim to have at least one group with 1 layer, one with 2 layers, and one with 3 layers in your set of targeting groups.

For each targeting group, briefly explain why you chose the specific number of layers you did, and how this structure helps target the ideal audience effectively.

You are forbidden from not using any audience that is not on the Audience Targeting Cheat Sheet.

Your response Should also be in plain text format for easy readability. Do not output in xml.

When listing the audiences in each layer, do not include the targeting type indicators (BT, IT, DT). Simply list the audience names separated by commas.

Note: For Reaching Medium to Large Enterprises can be challenging. Target people EMPLOYED by those larger companies, and then narrow by either the speciﬁc job title you're trying to reach or "management (demographic)".

Present your targeting groups in the following format:

<targeting_groups> Layer 1: (Option 1 (Type), Option 2 (Type), Option 3 (Type), Option 4 (Type), Option 5 (Type), Option 6 (Type), Option 7 (Type)) Layer 2: (Option 1 (Type), Option 2 (Type), Option 3 (Type), Option 4 (Type), Option 5 (Type), Option 6 (Type), Option 7 (Type)) Layer 3 (if applicable): (Option 1 (Type), Option 2 (Type), Option 3 (Type), Option 4 (Type), Option 5 (Type), Option 6 (Type), Option 7 (Type))  ... </targeting_groups>

After presenting the targeting groups, provide a brief explanation for each group, justifying your choices based on the offer and avatar descriptions. Use tags for this section.

Important considerations:

Choose targeting options based on what the ideal avatar may be searching for online if they're looking for help with the problem your offer solves.
Ensure that each layer narrows the audience appropriately for pinpoint targeting.
Use a mix of interest, behavior, and demographic targeting when relevant.
Avoid modifying or extending the provided targeting options in the cheat sheet.

Begin your analysis and targeting group creation now.

Here is the Audience Targeting Cheat Sheet:

Audience Targeting Cheat Sheet

Options in this category can be mixed and matched depending on who you're trying to reach. For example, if you help people lose weight, you can select options from almost any of the categories below. Choose the targeting based on what your ideal client may be searching for on the internet if they're looking for help with the problem you solve.

Health & wellness

Weight Loss: Chalene Johnson Diet Fitness Eat Smart Eating Well Health and Wellness Healthy Diet Healthy Eating Recipes Healthy Food Low Carbing Among Friends Michelle Bridges Michelle Bridges 12-Week Body Transformation Natalie Jill Fit Physical Exercise Physical Fitness Simply Healthy Diets Sugar Substitute Tara Stile

Fitness: 10K Run 24 Hour Fitness 5K Run Anytime Fitness Ashtanga Vinyasa Yoga Athleta Bandha Yoga - The Scientific Keys BASI Pilates Beachbody (Employers) BeFIT Bianchi Bicycles Bicycling (magazine) Bike (magazine) Bikram Yoga Bodybuilding Bodybuilding & Fitness Bodybuilding.com Bowflex Bryan Kest's Power Yoga Cannondale Bicycle Corporation Canyon Bicycles Cervélo Colnago CrossFit CrossFit Central CrossFit Games CrossFit Invictus CrossFit Mayhem CrossFit Sport Crossfit Training Crunch Fitness Cycling Cycling Club Cycling Team Cyclingnews.com CytoSport Danette May Diamondback Bicycles Equinox Fitness Fabletics Female Bodybuilding Fitbit Fitness (magazine) Fitness and Figure Competition GoodLife Fitness Half Marathon Hatha Yoga Health Club Hot Yoga I Love Crossfit Indoor cycling International Federation of BodyBuilding & Fitness Iron Force Ironman 70.3 Ironman Triathlon Ironman World Championship Isha Yoga Iyengar Yoga Jay Cutler (bodybuilder) Joseph Pilates Kai Greene Karma Yoga Kundalini Yoga LA Fitness Life Time Fitness Lululemon Athletica Marathons Mavic Men's Fitness Men's Health (magazine) Mini Marathon Muscle & Fitness MyFitnessPal Natural Bodybuilding Noah Mazé Yoga NordicTrack Orbea Oxygen Magazine Peloton Peloton Magazine Physical Exercise Physio Pilates Pilates Pilates Anytime Pinarello Planet Fitness Powerlifting Prevention (magazine) Rāja Yoga Rogue Fitness Ronnie Coleman Runner's World Running Running Club SCOTT Sports Self (magazine) Shimano Snap Fitness SoulCycle Specialized Bicycle Components SRAM Corporation Stott Pilates Studio Pilates Sweaty Betty The Bar Method The Yoga Teacher Trek Bicycle Corporation Ultramarathon USA Cycling USA Triathlon World Gym World Triathlon Corporation Yin Yoga Yoga Yoga Alliance Yoga Girl Yoga Journal Yoga Lin Zumba Fitness 2

Wellness: Biohacking Cholesterol Dave Asprey Dr. Josh Axe Drive to Stop Diabetes 300 Functional Fitness Mindbodygreen Natural Foods Natural Product Organic Food Organic Product RobbWolf.com Sara Gottfried, M.D. The Dr. Oz Show The Institute for Functional Medicine

Nutrition: BrooklynVegan Clean Eating Online Geneen Roth Gluten Institute for Integrative Nutrition Just Eat Real Food Kris Carr Lisa the Vegetarian Mee Eat Paleo Michelle Tam Nourished Kitchen Organic Food Paleo Paleo Grubs Paleo On The Go Paleoaholic - Eat Real Food Paleolithic Diet PaleOMG Plant-based diet Premier Protein Seane Corn The Nourished Life The Paleo Diet The Paleo Mom The Paleo Secret The Raw Food Kitchen Vegan Nutrition Vegetarian Cuisine Vegetarian Times Wheat Belly

Relationships

Dating: Blind Dating Bumble Eat Pray Love Gary Chapman (author) Hinge John Gray (U.S. author) Love Matthew Hussey

Divorce: Divorce Court Divorce Family Law Legal Separation

Relationship Statuses: Divorced Separated Unspecified Divorced Married Single Unspecified Widowed Unspecified

Parenting:

Parenting: 24/7 MOMS 4moms ABCmouse.com Early Learning Academy ACT (test) BabyCenter Babyganics Babyshop Britax Bustle Buy Buy Baby Carter's Chicco College College Admissions in the United States Confessions of a Homeschooler Cool Mom Picks Cybex International DANCOW Parenting Center Early Childhood Education Early Learning Centre ERGO Baby Fans of Being a Mom Graco (baby products) Great Homeschool Conventions Gymboree HelloGiggles High school High School Sports Magazine Higher Education Hip Homeschool Moms Homeschool Buyers Co-op Homeschooling Homeschooling in the United States Homeschooling Today (magazine) Hot Moms Club Khan Academy Kindergarten Life of Dad Little Passports Mamas & Papas Maria Montessori Middle school mom.me Mom's Got Ink MommyPage Montessori Education Motherhood In-Style Magazine Motherhood Maternity OshKosh B'Gosh Parenting (magazine) Parenting Styles Parenting Teenagers Parents (magazine) Peaceful Parenting Peg Perego Petit Bateau Philips AVENT PopSugar Positive Parenting Solutions Positive Parenting: Toddlers and Beyond Practical Homeschooling Pre-Kindergarten Pregnancy & Birth (magazine) Pregnancy and Newborn Magazine Pregnancy (magazine) Preschool Private School Private University Public University SAT Scary Mommy Scholarship Simple Homeschool Smart Parenting Magazine Student financial aid in the United States Test Preparation The Bump The Children's Place The Honest Company Toddler Approved Toilet Training Undergraduate Education University University and College Admission

Family Statuses: Parents (All) New Parents (0-12 months) Parents with toddlers (01-02 years) Parents with preschoolers (03-05 years) Parents with early school-age children (06-08 years) Parents with preteens (09-12 years) Parents with teenagers (13-17 years) Parents with adult children (18-26 years)

Faith & Spirituality

Christians: Bethany Hamilton Candace Cameron Bure Christ the Redeemer Compassion International Dave Ramsey Hobby Lobby Keeping the Faith Les Brown (speaker) Rachel Cruz Sadie Robertson Servant Leadership Southern methodist university Texas Christian University The Passion of the Christ Tim Tebow Tori Kelly UPtv

Spirituality: Byron Katie Gaia Online Illusion of Gaia Metaphysics Paulo Coelho Reiki Master Sonia Choquette

COACHING & Consulting

COACHING & Consulting: ActionCOACH Alexis Neely Ali Brown Allison Maslan Brendon Burchard Brendon Burchard - Live.Love.Matter. Emily Williams Fabienne Fredrickson Female Entrepreneur Association Institute for Integrative Nutrition (school) iPEC Coaching John C. Maxwell Kendall SummerHawk Lewis Howes Lisa Nichols Marie Forleo Michael Hyatt TISOC The International School Of Coaching

Job Titles: Business Management Consultant Business Process Consultant Career Coach Executive Coach Life Coach Life Skills Coach Marketing Consultant Personal Coach Personal Development Mentor Wellness Coach

PERSONAL DEVELOPMENT

Thought Leaders: Brian Tracy Dean Graziosi Jack Canfield Jim Rohn Napoleon Hill Richard Branson Robert Kiyosaki Seth Godin Simon Sinek Stephen Covey Tim Ferriss Zig Ziglar

Personal development: Anne Lamott Brené Brown Cheryl Richardson Darren Hardy Dean Graziosi Elizabeth Gilbert Jack Canfield James Altucher Jessica Ortner Kate Northrup Landmark Worldwide Les Brown (speaker) Louise Hay Martha Beck Mindvalley Personal development Prince Ea StevenAitchison T. Harv Eker Lisa Nichols

Speakers: Motivational Speaking National Speakers Bureau Speakers Bureau TED (conference) Toastmasters International

Job Titles: Motivational Speaker Public Speaking Speaker

FINANCE & INVESTING

Investing: Asset Management Charles Schwab Corporation Commercial Investing E-Trade Edward Jones Investments Fidelity Investments Goldman Sachs Investing.com Investment Investment Banking Investment Management Investment Strategy Investopedia Jim Cramer JPMorgan Chase MarketWatch Merrill Lynch Morgan Stanley Morgan Stanley Wealth Management Return on Investment StockTwits TD Ameritrade The Motley Fool The Vanguard Group The Wealthy Investor Timothy Sykes Wealth Wealth Creation Wealth Management

Real Estate: Armando Montelongo Biggerpockets.com Creative Real Estate Investing National Apartment Association Property Investment Club Property Management Real Estate Development Real Estate Economics Real Estate Investing Real Estate Investment Association Real Estate Investment Club Real Estate Investment Network Real Estate Investment Trust Real Estate Investor Magazine Rich Dad Poor Dad Robert Kiyosaki

BUSINESS

Brick & Mortar Business Owners: BNI (organization) Business Networking Chamber of Commerce Entrepreneurs' Organization Payment System Point of Sale Retail Retail Page Admins Salesforce.com Small Business Software

Online Business Owners: Amy Porterfield Anik Singal Asana (software) Basecamp (company) Buffer (application) Business Page Admins (behavior) Constant Contact Coursera CreativeLive Dani Johnson Darren Rowse Dean Graziosi Duct Tape Marketing ewomennetwork Facebook Page Admins (behavior) Fiverr Frank Kern Gary Vaynerchuk HubSpot Infusionsoft Instapage James Wedmore Jasmine Star Jay Abraham Jon Loomer Digital Jonathan Budd Kim Garst Leonie Dawson Life on Fire lynda.com MailChimp Mari Smith Marketo Moz (marketing software) My Lead System PRO Neil Patel Optimizely Robin Sharma Russell Brunson Ryan Deiss Sandi Krakowski SEMrush Small Business Owners (demographic) Social Media Examiner Sprout Social Tim Ferriss Trello Udemy Zendesk

General Biz Owner Job Titles: Business Owner Co Owner Founder Owner Owner and CEO Owner and Founder Owner/Manager/CEO Owner/Managing Director

General Interest-Based Targeting: Advertising Advertising Campaign Adwords Affiliate Marketing Brand Management Business Marketing Business-to-Business Content Marketing Conversion Marketing Digital Marketing Email Marketing Exit Strategy Influencer Marketing Landing Page Lead Generation Marketing Marketing Automation Marketing Strategy Online Advertising Pay Per Click Performance-based Advertising Promotion Marketing Search Engine Marketing Search Engine Optimization Social Media Marketing Software as a Service Subscription Business Model Viral Marketing

e-Commerce: Distribution (business) Drop Shipping E-Comm E-commerce E-Commerce payment system Etsy Jack Ma Product (business) Shopify Wholesale Wish WooCommerce

Start Ups: 500 Startups Angel Investor Crowdfunding Dave McClure Equity Crowdfunding Indiegogo Kickstarter Seed Accelerator Startup Company Startup Ecosystem Startup Village Startup Weekend TechCrunch Venture Capital Y Combinator (company)

Biz Opp/Start a Business: Business opportunity Business plan Entrepreneurship Home business Passive income Screw the Nine to Five Self-employment Work

Employers: Accenture Amazon.com Apple Inc. Cigna Cisco Citi Dell Technologies Deloitte Deutsche Bank Ernst & Young ExxonMobil GE Goldman Sachs Google HCL Technologies HP IBM IBM Global Services Intel J.P. Morgan & Co. Johnson & Johnson JP Morgan JPMorgan Chase & Co. LG Merrill Lynch Microsoft Morgan Stanley Oracle Samsung Global Siemens Sony Electronics The Boeing Company UBS Unilever

Job Titles: Associate Vice President Chief Information Officer (CIO) Chief marketing officer Chief Technology Officer (CTO) Director of Marketing and Public Relations Director of Operations and Creative Services Director of Sales Director of Sales and Market Development Director of Sales and Marketing Director of Sales Marketing Executive Vice President (EVP) Head of Marketing Marketing Operations Director Marketing Vice President Operations Director Sales Director Senior management Vice President of Marketing Vice President of Operations Vice President of Sales Vice President Sales

Behaviors: Management

Career Growth: Career Development New job (people who started a new job in the last 6 months) Leadership Development Professional Development Training and Development

Job Hunting: CareerBuilder Employment Agency Employment Website Glassdoor Indeed.com Job Hunting JobStreet.com LinkedIn Monster.com ZipRecruiter

Leadership: Daniel H. Pink Jack Welch James C. Collins John C. Maxwell Ken Blanchard Leadership Leadership Development Leadership Studies Marshall Goldsmith Napoleon Hill Robin Sharma Simon Sinek Stephen Covey Tom Peters

Sales: Brian Tracy Jim Rohn Jordan Belfort Robert Cialdini Sales management Zig Ziglar

Job Titles: Area Sales Manager Business Development Executive Director of Sales Director of Sales and Market Development Director of Sales Marketing Director Sales and Marketing, District Sales Manager General Sales Manager Inside Sales Manager National Sales Manager Regional Sales Manager Sales and Marketing Manager Sales Consultant Sales Development Manager Sales Director Sales Leader Sales Manager Sales Professional Sales Specialist Sales Supervisor Sales Team Manager Senior Sales Consultant Senior Sales Director Senior Sales Manager Territory Sales Executive Territory Sales Manager Vice President Sales and Marketing

High income earners

High income earners: Art Auction Berkshire Hathaway Billionaire Boys Club (clothing retailer) Bridgestone Golf Business Jet Callaway Golf Company Christie's Christie's International Real Estate Cobra Golf Country Club Country Club Prep Delta Private Jets Four Seasons Hotels and Resorts Frieze Art Fair Golf Digest Golf Magazine Greystone Golf & Country Club High-Net-Worth Individual Household income: top 10% of ZIP codes (US) Household income: top 10%-25% of ZIP codes (US) Household income: top 5% of ZIP codes (US) Lahore Garrison Golf and Country Club Luxury Resorts Luxury yacht Mandarin Oriental Hotel Group Mizuno Golf North America Montage Beverly Hills Montage Deer Valley Montage Laguna Beach Nashville Country Club NetJets Oakmont Country Club Private Jets Ritz-Carlton Hotel Company Royal Palm Golf and Country Club Royal Yachting Association Savills Sotheby's Sotheby's International Realty Tatler TaylorMade Golf Pacific TaylorMade-Adidas Titleist Waldorf Astoria Hotels & Resorts XOJET Yacht club Yachting Yachting (magazine) Yachting World Yachts and Yachting Magazine

Network marketing

Network marketing: ACN AdvoCare Amway Arbonne Avon Beachbody Beachbody LLC Cutco Cutlery doTERRA Essential Oils USA Family Team It Works Independent Distributors Forever Living Products Herbalife Nutrition Herbalife24 Independent Team Beachbody Coach Isagenix® Jamberry Jeunesse Global LegalShield LifeVantage LuLaRoe Market America MARY KAY Melaleuca MLM MONAT Natura Nu Skin Organo Origami Owl Pampered Chef Paparazzi Accessories PartyLite PartyLite Candles Perfectly Posh Plexus Corp Plexus Worldwide Primerica Pruvit Pure Romance Rodan + Fields Scentsy Stella & Dot Team Beachbody Thirty-one Gifts USANA Health Sciences Inc. Usborne Books & More Younique Younique Independent Presenter Younique products

Job Titles: Avon Independent Beachbody Coach Independent Team Beachbody Coach Independent Younique Presenter Network Marketing Paparazzi

Employers: Arbonne Australia & New Zealand Arbonne Canada Arbonne UK MARY KAY MLM MONAT Network Marketing Rodan + Fields Younique

I only want a pure output of just the content and nothing else do not add any addional commentary before or after your output.

Each targeting group must have its explination after it.


 
OUTPUT MUST BE IN MARKDOWN LANGUAGE
