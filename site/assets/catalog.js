/* SHUNCHi catalogue: every app and free tool on the website, and the code that draws them.
   =====================================================================================
   PUBLISH A TOOL WHEN ITS PAGE IS READY
     1. Copy apps/_template.html to apps/<id>.html and build the tool inside it.
     2. In TOOLS below, change that tool's  s: "soon"  (or "next")  to  s: "live".
        Its page is apps/<id>.html automatically. Nothing else to edit.

   ADD A NEW TOOL IDEA     copy one line in TOOLS and change id, c (category key), t/d (English), tb/db (Bangla).
   ADD A NEW CATEGORY      copy one line in CATS.
   ADD A NEW DESKTOP APP   add an item to APPS (and to data/apps.json so it also shows inside SHUNCHi).

   s (status):  "live" = open now · "next" = being built now · "soon" = planned
*/
var CATS = [
  { k: "career",   en: "Career & jobs",        bn: "ক্যারিয়ার ও চাকরি",
    de: "Documents and profile help for job seekers.", db: "চাকরিপ্রার্থীদের ডকুমেন্ট ও প্রোফাইলের কাজ।" },
  { k: "business", en: "Business documents",   bn: "ব্যবসা ও ডকুমেন্ট",
    de: "Invoices, quotes and receipts that look professional.", db: "পেশাদার চেহারার ইনভয়েস, কোটেশন ও রিসিপ্ট।" },
  { k: "money",    en: "Money & budget",       bn: "টাকা ও বাজেট",
    de: "Plan, save and understand your money.", db: "টাকার হিসাব, সঞ্চয় ও বাজেট বুঝে নিন।" },
  { k: "daily",    en: "Daily life & travel",  bn: "দৈনন্দিন ও ভ্রমণ",
    de: "Small calculators for everyday decisions.", db: "দৈনন্দিন সিদ্ধান্তের জন্য ছোট ছোট ক্যালকুলেটর।" },
  { k: "health",   en: "Health & fitness",     bn: "স্বাস্থ্য ও ফিটনেস",
    de: "Simple health numbers, explained clearly.", db: "স্বাস্থ্যের সহজ হিসাব, পরিষ্কার ব্যাখ্যাসহ।" },
  { k: "study",    en: "Study & exams",        bn: "পড়াশোনা ও পরীক্ষা",
    de: "Tools for students.", db: "শিক্ষার্থীদের জন্য টুল।" },
  { k: "bangla",   en: "Bangla & text",        bn: "বাংলা ও টেক্সট",
    de: "Work with Bangla text without the hassle.", db: "বাংলা লেখা নিয়ে ঝামেলাহীন কাজ।" },
  { k: "media",    en: "Images & files",       bn: "ছবি ও ফাইল",
    de: "Quick fixes for photos and documents, in your browser.", db: "ছবি ও ডকুমেন্টের দ্রুত কাজ, ব্রাউজারেই।" },
  { k: "voice",    en: "Voice & AI",           bn: "ভয়েস ও এআই",
    de: "More ways to use your voice, from the makers of SHUNCHi.", db: "SHUNCHi-র নির্মাতাদের কাছ থেকে কণ্ঠ ব্যবহারের আরও উপায়।" }
];

var APPS = [
  { name: "SHUNCHi", en: "AI voice typing for Bangla and English, in every Windows app.",
    bn: "প্রতিটি উইন্ডোজ অ্যাপে বাংলা ও ইংরেজি এআই ভয়েস টাইপিং।",
    url: "download/index.html", more: "index.html", badge: "v4", s: "live", logo: "assets/shunchi-icon.png" },
  { name: "My next app / software", nb: "আমার পরবর্তী অ্যাপ / সফটওয়্যার", en: "Submit your idea in the form below.",
    bn: "আপনার আইডিয়া নিচের ফর্মে জমা দিন।", url: "", badge: "", s: "soon", logo: "", idea: true }
];

var TOOLS = [
  // ---- Career & jobs
  { id: "build-cv", c: "career", s: "next", t: "CV Builder", tb: "সিভি বিল্ডার",
    d: "A clean, ATS-friendly CV from 15 templates and 24 colour themes.",
    db: "১৫টি টেমপ্লেট ও ২৪টি রঙের থিমে পরিচ্ছন্ন, ATS-বান্ধব সিভি।" },
  { id: "cover-letter", c: "career", s: "soon", t: "Cover Letter Builder", tb: "কভার লেটার বিল্ডার",
    d: "Write a polished cover letter with ready presets and a live letterhead preview.",
    db: "তৈরি প্রিসেট ও লাইভ লেটারহেড প্রিভিউ দিয়ে গোছানো কভার লেটার লিখুন।" },
  { id: "resignation-letter", c: "career", s: "soon", t: "Resignation Letter", tb: "পদত্যাগপত্র",
    d: "A formal resignation letter with your notice period and handover note. PDF or Word.",
    db: "নোটিশ পিরিয়ড ও হস্তান্তরের নোটসহ আনুষ্ঠানিক পদত্যাগপত্র। PDF বা Word।" },
  { id: "achievement-card", c: "career", s: "soon", t: "Achievement Card", tb: "অর্জনের কার্ড",
    d: "Design a branded card for a milestone and share it on LinkedIn, X or WhatsApp.",
    db: "মাইলফলকের জন্য ব্র্যান্ডেড কার্ড বানিয়ে LinkedIn, X বা WhatsApp-এ শেয়ার করুন।" },
  { id: "linkedin-helper", c: "career", s: "soon", t: "LinkedIn Helper", tb: "LinkedIn সহায়ক",
    d: "Draft your headline and About section, style your posts and review your profile.",
    db: "হেডলাইন ও About লিখুন, পোস্ট সাজান এবং প্রোফাইল যাচাই করুন।" },
  { id: "bdjobs-helper", c: "career", s: "soon", t: "Bdjobs Helper", tb: "Bdjobs সহায়ক",
    d: "Improve your search ranking, write application notes and prepare for interviews.",
    db: "সার্চ র‍্যাংকিং বাড়ান, আবেদনের নোট লিখুন এবং ইন্টারভিউয়ের প্রস্তুতি নিন।" },
  { id: "interview-prep", c: "career", s: "soon", t: "Interview Practice Cards", tb: "ইন্টারভিউ প্র্যাকটিস কার্ড",
    d: "Common questions with answer tips. Practise by flipping cards.",
    db: "প্রচলিত প্রশ্ন ও উত্তরের টিপস। কার্ড উল্টে অনুশীলন করুন।" },
  { id: "job-tracker", c: "career", s: "soon", t: "Job Application Tracker", tb: "আবেদন ট্র্যাকার",
    d: "Keep every application, deadline and follow-up in one list.",
    db: "প্রতিটি আবেদন, শেষ তারিখ ও ফলো-আপ এক তালিকায় রাখুন।" },
  // ---- Business documents
  { id: "invoice-maker", c: "business", s: "next", t: "Invoice Maker", tb: "ইনভয়েস মেকার",
    d: "Invoices with line items, multiple currencies, VAT and a print-ready A4 PDF.",
    db: "আইটেম, একাধিক মুদ্রা ও ভ্যাটসহ ইনভয়েস। প্রিন্টের উপযোগী A4 PDF।" },
  { id: "quotation-maker", c: "business", s: "soon", t: "Quotation Maker", tb: "কোটেশন মেকার",
    d: "Price quotes and proposals with validity date, terms and a signature block.",
    db: "মেয়াদ, শর্ত ও স্বাক্ষরের জায়গাসহ কোটেশন ও প্রস্তাবনা।" },
  { id: "money-receipt", c: "business", s: "soon", t: "Money Receipt", tb: "মানি রিসিপ্ট",
    d: "Simple payment receipts with the amount written in words.",
    db: "কথায় টাকার অঙ্কসহ সহজ পেমেন্ট রিসিপ্ট।" },
  { id: "delivery-challan", c: "business", s: "soon", t: "Delivery Challan", tb: "ডেলিভারি চালান",
    d: "A neat challan for goods you send, ready to print.",
    db: "পাঠানো পণ্যের জন্য গোছানো চালান, প্রিন্টের জন্য তৈরি।" },
  { id: "business-card", c: "business", s: "soon", t: "Business Card Maker", tb: "ভিজিটিং কার্ড মেকার",
    d: "Design a visiting card and download it for print.",
    db: "ভিজিটিং কার্ড ডিজাইন করে প্রিন্টের জন্য নামিয়ে নিন।" },
  { id: "letterhead", c: "business", s: "soon", t: "Letterhead Maker", tb: "লেটারহেড মেকার",
    d: "A clean letterhead with your logo and contact details.",
    db: "আপনার লোগো ও যোগাযোগের তথ্যসহ পরিচ্ছন্ন লেটারহেড।" },
  // ---- Money & budget
  { id: "budget-calculator", c: "money", s: "next", t: "Budget Calculator", tb: "বাজেট ক্যালকুলেটর",
    d: "Split your monthly income into needs, wants and savings, and see where the money goes.",
    db: "মাসিক আয়কে প্রয়োজন, চাহিদা ও সঞ্চয়ে ভাগ করুন এবং দেখুন টাকা কোথায় যাচ্ছে।" },
  { id: "loan-emi", c: "money", s: "soon", t: "Loan EMI Calculator", tb: "ঋণের কিস্তি ক্যালকুলেটর",
    d: "Monthly instalment, total interest and a repayment schedule.",
    db: "মাসিক কিস্তি, মোট সুদ ও পরিশোধের সূচি।" },
  { id: "savings-calculator", c: "money", s: "soon", t: "Savings & FDR Calculator", tb: "সঞ্চয় ও এফডিআর ক্যালকুলেটর",
    d: "See how a deposit or monthly saving grows over time.",
    db: "জমা বা মাসিক সঞ্চয় সময়ের সাথে কীভাবে বাড়ে দেখুন।" },
  { id: "salary-calculator", c: "money", s: "soon", t: "Take-home Salary", tb: "হাতে পাওয়া বেতন",
    d: "Estimate your take-home pay in BDT from gross salary.",
    db: "মোট বেতন থেকে টাকায় হাতে পাওয়া বেতনের আনুমানিক হিসাব।" },
  { id: "zakat-calculator", c: "money", s: "soon", t: "Zakat Calculator", tb: "যাকাত ক্যালকুলেটর",
    d: "Work out zakat on your savings, gold and business assets.",
    db: "সঞ্চয়, স্বর্ণ ও ব্যবসার সম্পদের যাকাত হিসাব করুন।" },
  { id: "percentage-calculator", c: "money", s: "soon", t: "Percentage & Discount", tb: "শতকরা ও ছাড়",
    d: "Percentages, discounts and price changes in one place.",
    db: "শতকরা, ছাড় ও দামের পরিবর্তন এক জায়গায়।" },
  { id: "profit-margin", c: "money", s: "soon", t: "Profit Margin Calculator", tb: "লাভের হার ক্যালকুলেটর",
    d: "Cost, selling price and margin for small businesses.",
    db: "ছোট ব্যবসার জন্য খরচ, বিক্রয়মূল্য ও লাভের হার।" },
  { id: "currency-converter", c: "money", s: "soon", t: "Currency Converter", tb: "মুদ্রা কনভার্টার",
    d: "Convert BDT and major currencies at current rates.",
    db: "টাকা ও প্রধান মুদ্রা বর্তমান দরে রূপান্তর করুন।" },
  // ---- Daily life & travel
  { id: "tour-calculator", c: "daily", s: "next", t: "Tour Calculator", tb: "ট্যুর ক্যালকুলেটর",
    d: "Plan a trip budget: transport, stay, food and extras, with the cost per person.",
    db: "ভ্রমণের বাজেট করুন: যাতায়াত, থাকা, খাওয়া ও অন্যান্য খরচ, জনপ্রতি হিসাবসহ।" },
  { id: "bill-splitter", c: "daily", s: "soon", t: "Bill Splitter", tb: "বিল ভাগ করুন",
    d: "Split a bill or shared expenses fairly among friends.",
    db: "বন্ধুদের মধ্যে বিল বা যৌথ খরচ ন্যায্যভাবে ভাগ করুন।" },
  { id: "calculator", c: "daily", s: "soon", t: "Calculator", tb: "ক্যালকুলেটর",
    d: "Standard and scientific modes with keyboard shortcuts and a history tape.",
    db: "স্ট্যান্ডার্ড ও সায়েন্টিফিক মোড, কীবোর্ড শর্টকাট ও হিস্ট্রি টেপসহ।" },
  { id: "age-calculator", c: "daily", s: "soon", t: "Age Calculator", tb: "বয়স ক্যালকুলেটর",
    d: "Your exact age, a countdown to the next birthday and life milestones.",
    db: "সঠিক বয়স, পরবর্তী জন্মদিনের কাউন্টডাউন ও জীবনের মাইলফলক।" },
  { id: "unit-converter", c: "daily", s: "soon", t: "Unit Converter", tb: "একক কনভার্টার",
    d: "Length, weight, area (including katha and bigha), temperature and more.",
    db: "দৈর্ঘ্য, ওজন, ক্ষেত্রফল (কাঠা-বিঘাসহ), তাপমাত্রা ও আরও অনেক কিছু।" },
  { id: "date-difference", c: "daily", s: "soon", t: "Date Difference", tb: "তারিখের ব্যবধান",
    d: "Days, weeks and months between two dates.",
    db: "দুই তারিখের মধ্যে কত দিন, সপ্তাহ ও মাস।" },
  // ---- Health & fitness
  { id: "bmi-calculator", c: "health", s: "soon", t: "BMI Calculator", tb: "BMI ক্যালকুলেটর",
    d: "BMI on a visual gauge with a healthy weight range.",
    db: "ভিজ্যুয়াল গেজে BMI এবং সুস্থ ওজনের পরিসর।" },
  { id: "calorie-calculator", c: "health", s: "soon", t: "Calorie & BMR", tb: "ক্যালরি ও BMR",
    d: "Daily calorie needs for your age, weight and activity.",
    db: "বয়স, ওজন ও কাজের ধরন অনুযায়ী দৈনিক ক্যালরির প্রয়োজন।" },
  { id: "water-intake", c: "health", s: "soon", t: "Water Intake", tb: "পানির চাহিদা",
    d: "How much water to drink each day, with a simple tracker.",
    db: "প্রতিদিন কতটা পানি পান করবেন, সহজ ট্র্যাকারসহ।" },
  { id: "sleep-calculator", c: "health", s: "soon", t: "Sleep Calculator", tb: "ঘুমের ক্যালকুলেটর",
    d: "Find the best bedtime or wake-up time using sleep cycles.",
    db: "ঘুমের চক্র ধরে ঘুমানো বা জাগার সেরা সময় জানুন।" },
  // ---- Study & exams
  { id: "cgpa-calculator", c: "study", s: "soon", t: "CGPA Calculator", tb: "CGPA ক্যালকুলেটর",
    d: "Calculate GPA and CGPA from your grades and credits.",
    db: "গ্রেড ও ক্রেডিট থেকে GPA ও CGPA হিসাব করুন।" },
  { id: "marks-calculator", c: "study", s: "soon", t: "Marks & Percentage", tb: "নম্বর ও শতকরা",
    d: "Total marks, percentage and grade in a few taps.",
    db: "মোট নম্বর, শতকরা ও গ্রেড কয়েকটি ট্যাপেই।" },
  { id: "pomodoro", c: "study", s: "soon", t: "Pomodoro Timer", tb: "পোমোডোরো টাইমার",
    d: "Focus in short rounds with timed breaks.",
    db: "ছোট ছোট রাউন্ডে মন দিয়ে পড়ুন, মাঝে বিরতিসহ।" },
  { id: "study-planner", c: "study", s: "soon", t: "Study Planner", tb: "পড়ার রুটিন",
    d: "Turn your syllabus and exam date into a weekly plan.",
    db: "সিলেবাস ও পরীক্ষার তারিখ থেকে সাপ্তাহিক রুটিন বানান।" },
  { id: "exam-countdown", c: "study", s: "soon", t: "Exam Countdown", tb: "পরীক্ষার কাউন্টডাউন",
    d: "Days left for every exam you add.",
    db: "যোগ করা প্রতিটি পরীক্ষার বাকি দিন।" },
  // ---- Bangla & text
  { id: "word-counter", c: "bangla", s: "soon", t: "Word & Character Counter", tb: "শব্দ ও অক্ষর কাউন্টার",
    d: "Count words, characters and sentences in Bangla or English, with reading time.",
    db: "বাংলা বা ইংরেজি লেখার শব্দ, অক্ষর ও বাক্য গুনুন, সাথে পড়ার সময়।" },
  { id: "taka-in-words", c: "bangla", s: "soon", t: "Taka in Words", tb: "কথায় টাকা",
    d: "Write an amount in words in Bangla and English for cheques and invoices.",
    db: "চেক ও ইনভয়েসের জন্য টাকার অঙ্ক বাংলা ও ইংরেজি কথায় লিখুন।" },
  { id: "bijoy-unicode", c: "bangla", s: "soon", t: "Bijoy ⇄ Unicode", tb: "বিজয় ⇄ ইউনিকোড",
    d: "Convert old Bijoy text to Unicode and back in one click.",
    db: "পুরনো বিজয় লেখা ইউনিকোডে আর ইউনিকোড বিজয়ে বদলান এক ক্লিকে।" },
  { id: "bangla-date", c: "bangla", s: "soon", t: "Bangla Date Converter", tb: "বাংলা তারিখ কনভার্টার",
    d: "Convert between English and Bangla calendar dates.",
    db: "ইংরেজি ও বাংলা সনের তারিখ পরস্পরে বদলান।" },
  { id: "text-cleaner", c: "bangla", s: "soon", t: "Text Cleaner", tb: "টেক্সট ক্লিনার",
    d: "Remove extra spaces and line breaks, fix case and sort lines.",
    db: "বাড়তি ফাঁকা জায়গা ও লাইন ব্রেক সরান, কেস ঠিক করুন, লাইন সাজান।" },
  { id: "bangla-typing", c: "bangla", s: "soon", t: "Bangla Typing Practice", tb: "বাংলা টাইপিং অনুশীলন",
    d: "Practise Bangla typing with speed and accuracy scores.",
    db: "গতি ও নির্ভুলতার স্কোরসহ বাংলা টাইপিং অনুশীলন।" },
  // ---- Images & files
  { id: "qr-code", c: "media", s: "next", t: "QR Code Maker", tb: "QR কোড মেকার",
    d: "A QR code for a link, Wi-Fi or contact, downloaded as PNG.",
    db: "লিংক, Wi-Fi বা কন্টাক্টের QR কোড, PNG হিসেবে নামান।" },
  { id: "photo-resizer", c: "media", s: "soon", t: "Photo Resizer", tb: "ছবি রিসাইজার",
    d: "Resize photos for CVs, forms and uploads without leaving your browser.",
    db: "সিভি, ফর্ম ও আপলোডের মাপে ছবি রিসাইজ করুন, ব্রাউজার ছেড়ে না গিয়েই।" },
  { id: "image-compressor", c: "media", s: "soon", t: "Image Compressor", tb: "ছবি কম্প্রেসার",
    d: "Make images smaller while keeping them sharp.",
    db: "ছবির মান ঠিক রেখে ফাইলের আকার ছোট করুন।" },
  { id: "pdf-tools", c: "media", s: "soon", t: "PDF Merge & Split", tb: "PDF জোড়া ও ভাগ",
    d: "Combine PDFs or pull out the pages you need.",
    db: "PDF জোড়া লাগান বা দরকারি পাতাগুলো আলাদা করুন।" },
  { id: "passport-photo", c: "media", s: "soon", t: "Passport Photo Maker", tb: "পাসপোর্ট ছবি মেকার",
    d: "Crop to passport and visa sizes and print several on one sheet.",
    db: "পাসপোর্ট ও ভিসার মাপে কেটে এক পাতায় কয়েকটি ছবি প্রিন্ট করুন।" },
  // ---- Voice & AI
  { id: "voice-notes", c: "voice", s: "soon", t: "Voice Notes", tb: "ভয়েস নোট",
    d: "Speak in your browser and get clean, punctuated text.",
    db: "ব্রাউজারে কথা বলুন, দাঁড়ি-কমাসহ গোছানো লেখা পান।" },
  { id: "meeting-notes", c: "voice", s: "soon", t: "Meeting Notes", tb: "মিটিং নোট",
    d: "Turn a recording into a short summary with action points.",
    db: "রেকর্ডিং থেকে সংক্ষিপ্ত সারসহ করণীয় তালিকা বানান।" },
  { id: "text-reader", c: "voice", s: "soon", t: "Bangla Text Reader", tb: "বাংলা টেক্সট রিডার",
    d: "Listen to Bangla text read aloud.",
    db: "বাংলা লেখা পড়ে শোনানো হবে, আপনি শুধু শুনুন।" },
  { id: "subtitle-maker", c: "voice", s: "soon", t: "Subtitle Maker", tb: "সাবটাইটেল মেকার",
    d: "Create SRT subtitles from audio or video speech.",
    db: "অডিও বা ভিডিওর কথা থেকে SRT সাবটাইটেল বানান।" }
];

(function () {
  var script = document.currentScript;
  var BASE = (script && script.getAttribute("data-base")) || "";
  var STATUS = {
    live: { en: "Live", bn: "চালু", cls: "live" },
    next: { en: "Next up", bn: "পরবর্তী", cls: "next" },
    soon: { en: "Planned", bn: "পরিকল্পনায়", cls: "" }
  };
  var ICONS = {
    career: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>',
    business: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>',
    money: '<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 9v.01M18 15v.01"/>',
    daily: '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
    health: '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
    study: '<path d="M3 9l9-5 9 5-9 5z"/><path d="M7 11.5V16c0 1.5 2.2 3 5 3s5-1.5 5-3v-4.5"/>',
    bangla: '<path d="M4 5h9M8.5 3v2M6 9c1.2 3 3.8 5 7 6M12 5c-.5 4-3 8-8 10"/><path d="M13 21l4-10 4 10M14.5 18h5"/>',
    media: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-4-8 7"/>',
    voice: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'
  };

  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
  function bi(en, bn) { var b = document.createElement("span"); b.appendChild(el("span", "en", en)); b.appendChild(el("span", "bn", bn)); return b; }
  function cat(k) { return CATS.filter(function (c) { return c.k === k; })[0]; }
  function toolUrl(t) { return BASE + "apps/" + t.id + ".html"; }
  function rank(t) { return t.s === "live" ? 0 : t.s === "next" ? 1 : 2; }

  function statusBadge(s) {
    var m = STATUS[s] || STATUS.soon, b = el("span", "badge" + (m.cls ? " " + m.cls : ""));
    b.appendChild(bi(m.en, m.bn)); return b;
  }

  /* ---- tool card ---- */
  function toolCard(t) {
    var live = t.s === "live";
    var node = el(live ? "a" : "div", "tool" + (live ? " is-live" : ""));
    if (live) node.href = toolUrl(t);
    var icon = el("div", "tool-icon");
    icon.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[t.c] || ICONS.media) + "</svg>";
    var body = el("div", "tool-body");
    var h = el("h3"); h.appendChild(bi(t.t, t.tb));
    var p = el("p"); p.appendChild(bi(t.d, t.db));
    body.appendChild(h); body.appendChild(p);
    var foot = el("div", "tool-foot");
    var c = cat(t.c); var cs = el("span", "tool-cat"); if (c) cs.appendChild(bi(c.en, c.bn));
    foot.appendChild(cs); foot.appendChild(statusBadge(t.s));
    node.appendChild(icon); node.appendChild(body); node.appendChild(foot);
    return node;
  }

  /* renderTools(container, { cat: key|"all", q: "search text", limit: n, grouped: bool }) */
  window.renderTools = function (container, o) {
    o = o || {}; container.textContent = "";
    var q = (o.q || "").trim().toLowerCase();
    var list = TOOLS.filter(function (t) {
      if (o.cat && o.cat !== "all" && t.c !== o.cat) return false;
      if (!q) return true;
      return (t.t + " " + t.tb + " " + t.d + " " + t.db + " " + t.id).toLowerCase().indexOf(q) >= 0;
    });
    list.sort(function (a, b) { return rank(a) - rank(b); });
    if (o.featured) {
      /* hand-picked most powerful tools, in this order (used on the home page) */
      list = o.featured.map(function (id) { return TOOLS.filter(function (t) { return t.id === id; })[0]; }).filter(Boolean);
    }
    if (o.limit) list = list.slice(0, o.limit);
    if (!list.length) {
      var none = el("p", "empty"); none.appendChild(bi("No tool matches your search yet. Tell us what you need and we will add it.", "এই নামে কোনো টুল এখনও নেই। কী দরকার জানান, আমরা যোগ করব।"));
      container.appendChild(none); return 0;
    }
    if (o.grouped && (!o.cat || o.cat === "all") && !q) {
      CATS.forEach(function (c) {
        var items = list.filter(function (t) { return t.c === c.k; });
        if (!items.length) return;
        var section = el("section", "cat-block"); section.id = "cat-" + c.k;
        var head = el("div", "cat-head");
        var h = el("h3"); h.appendChild(bi(c.en, c.bn));
        var count = el("span", "cat-count", String(items.length));
        head.appendChild(h); head.appendChild(count);
        var d = el("p", "cat-desc"); d.appendChild(bi(c.de, c.db));
        var grid = el("div", "tools");
        items.forEach(function (t) { grid.appendChild(toolCard(t)); });
        section.appendChild(head); section.appendChild(d); section.appendChild(grid);
        container.appendChild(section);
      });
    } else {
      var grid2 = el("div", "tools");
      list.forEach(function (t) { grid2.appendChild(toolCard(t)); });
      container.appendChild(grid2);
    }
    reveal(container);
    return list.length;
  };

  /* Staggered fade-up when cards scroll into view. Without JS or with reduced motion, cards just show. */
  function reveal(container) {
    var cards = container.querySelectorAll(".tool");
    var calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm || !("IntersectionObserver" in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    cards.forEach(function (c, i) {
      c.classList.add("rv"); c.style.setProperty("--d", (i % 6) * 70 + "ms"); io.observe(c);
    });
  }

  /* category chips with counts: renderCategoryTabs(container, onPick) */
  window.renderCategoryTabs = function (container, onPick) {
    container.textContent = "";
    var all = [{ k: "all", en: "All", bn: "সব" }].concat(CATS);
    all.forEach(function (c, i) {
      var n = c.k === "all" ? TOOLS.length : TOOLS.filter(function (t) { return t.c === c.k; }).length;
      var b = el("button", "chip"); b.type = "button"; b.setAttribute("aria-pressed", i === 0 ? "true" : "false");
      b.appendChild(bi(c.en, c.bn)); b.appendChild(el("span", "chip-n", String(n)));
      b.addEventListener("click", function () {
        container.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true"); onPick(c.k);
      });
      container.appendChild(b);
    });
  };

  /* ---- app rows ---- */
  function appRow(a) {
    var live = a.s === "live" && a.url;
    var node = el("div", "app-row" + (live ? "" : " is-soon"));
    var tile = el("div", "app-tile");
    if (a.logo) { var img = document.createElement("img"); img.src = BASE + a.logo; img.alt = ""; tile.appendChild(img); }
    else tile.textContent = (a.name || "?").charAt(0).toUpperCase();
    var body = el("div", "app-body");
    var h = el("h3"); if (a.nb) h.appendChild(bi(a.name, a.nb)); else h.textContent = a.name; if (a.badge) h.appendChild(el("span", "ver", a.badge));
    var p = el("p"); p.appendChild(bi(a.en || "", a.bn || a.en || ""));
    body.appendChild(h); body.appendChild(p);
    var act = el("div", "app-act");
    if (live) {
      var go = el("a", "btn btn-primary btn-sm"); go.href = /^https?:/.test(a.url) ? a.url : BASE + a.url;
      var isDl = a.name === "SHUNCHi" || a.dl;
      go.appendChild(bi(isDl ? "Download" : "Open", isDl ? "ডাউনলোড" : "খুলুন"));
      act.appendChild(go);
      if (a.more) { var m = el("a", "btn btn-ghost btn-sm"); m.href = BASE + a.more; m.appendChild(bi("Details", "বিস্তারিত")); act.appendChild(m); }
    } else if (a.idea) {
      var ib = el("a", "btn btn-primary btn-sm"); ib.href = "#suggest";
      ib.appendChild(bi("Submit idea", "আইডিয়া দিন")); act.appendChild(ib);
    } else act.appendChild(statusBadge("soon"));
    node.appendChild(tile); node.appendChild(body); node.appendChild(act);
    return node;
  }
  var appsView = APPS;
  window.renderApps = function (container, limit) {
    container.textContent = "";
    var list = limit ? appsView.slice(0, limit) : appsView;
    list.forEach(function (a) { container.appendChild(appRow(a)); });
  };

  /* Apps published from the release panel / GitHub release appear here without editing this file. */
  window.loadRemoteApps = function (done) {
    if (!window.fetch || location.protocol.indexOf("http") !== 0) return;
    /* Software added in the admin panel (data/apps.json) and anything listed in update.json */
    fetch(BASE + "data/apps.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; }).then(function (list) {
      var extra = (list || []).filter(function (a) { return a && a.id && a.name && (a.status || "live") === "live"; }).map(function (a) {
        return { name: a.name, en: a.tagline_en || a.tagline || "", bn: a.tagline_bn || a.tagline_en || a.tagline || "", url: a.url || "", badge: a.version || "",
                 s: "live", logo: a.logo || "", more: "apps/" + a.id + ".html", dl: true };
      });
      if (extra.length) { appsView = [APPS[0]].concat(extra, APPS.slice(1)); }
      if (done) done();
    });
  };
  window.SITE_COUNTS = function () { return { tools: TOOLS.length, cats: CATS.length }; };
})();
