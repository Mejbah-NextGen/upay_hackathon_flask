"""Deterministic UI translations; identifiers and editable user values stay intact."""
from html import escape
from html.parser import HTMLParser
import re

BANGLA = {
    "Dashboard": "ড্যাশবোর্ড", "Home": "হোম", "Payment": "পেমেন্ট", "Payments": "পেমেন্ট",
    "Welcome,": "স্বাগতম,", "Registered": "নিবন্ধিত", "Verified account": "যাচাইকৃত অ্যাকাউন্ট", "Authorizing provider": "অনুমোদনকারী সেবাদাতা",
    "Services": "সেবা", "All Services": "সব সেবা", "Quick Services": "দ্রুত সেবা",
    "Quick Payment": "দ্রুত পেমেন্ট", "Popular": "জনপ্রিয়", "See All": "সব দেখুন",
    "Send Money": "টাকা পাঠান", "Transfer Money": "টাকা ট্রান্সফার", "Add Money": "টাকা যোগ করুন",
    "Cash Out": "ক্যাশ আউট", "Cash Out (Agent / ATM)": "ক্যাশ আউট (এজেন্ট / এটিএম)",
    "Financial Services": "আর্থিক সেবা", "Other Services": "অন্যান্য সেবা", "Profile": "প্রোফাইল",
    "My Profile": "আমার প্রোফাইল", "Report": "রিপোর্ট", "Auto Pay": "অটো পে", "Logout": "লগ আউট",
    "Notifications": "নোটিফিকেশন", "View all": "সব দেখুন", "Mark all as read": "সব পড়া হয়েছে",
    "Unread": "অপঠিত", "Read": "পঠিত", "View details": "বিস্তারিত দেখুন", "Open details": "বিস্তারিত দেখুন",
    "Transaction notifications": "লেনদেনের নোটিফিকেশন", "Wallet activity": "ওয়ালেটের কার্যক্রম",
    "Updates from your transaction history in Bangladesh time.": "বাংলাদেশের সময় অনুযায়ী আপনার লেনদেনের আপডেট।",
    "No transactions yet. Your wallet activity will appear here.": "এখনও কোনো লেনদেন নেই। আপনার ওয়ালেটের কার্যক্রম এখানে দেখা যাবে।",
    "Transaction alerts are turned off.": "লেনদেনের নোটিফিকেশন বন্ধ রয়েছে।", "Manage settings": "সেটিংস পরিবর্তন করুন",
    "Notification settings": "নোটিফিকেশন সেটিংস", "Notification preferences": "নোটিফিকেশন পছন্দ",
    "Current Balance": "বর্তমান ব্যালেন্স", "Today's Transactions": "আজকের লেনদেন",
    "Today's Payments": "আজকের পেমেন্ট", "Today's Money Out": "আজকের খরচ",
    "Transactions": "লেনদেন", "View Transactions": "লেনদেন দেখুন", "Payment Details": "পেমেন্টের বিস্তারিত",
    "View Money Out": "খরচ দেখুন", "Money Out": "খরচ", "Balance": "ব্যালেন্স", "Wallet Balance": "ওয়ালেট ব্যালেন্স",
    "Today": "আজ", "Today's": "আজকের", "Today’s": "আজকের", "Today’s activity": "আজকের কার্যক্রম",
    "Today activity": "আজকের কার্যক্রম", "Today's activity": "আজকের কার্যক্রম", "Days (1–120)": "দিন (১–১২০)",
    "7 days": "৭ দিন", "30 days": "৩০ দিন", "120 days": "১২০ দিন", "Apply": "প্রয়োগ করুন",
    "Your services and wallet activity in one place.": "আপনার সব সেবা ও ওয়ালেটের কার্যক্রম এক জায়গায়।",
    "Payments include completed bill payments and mobile recharge. Money out includes completed payments, transfers, cash-outs and fees. Your balance always shows the current amount.": "পেমেন্টে সফল বিল ও রিচার্জ দেখানো হয়। খরচে সফল পেমেন্ট, ট্রান্সফার, ক্যাশ আউট ও ফি অন্তর্ভুক্ত। ব্যালেন্স সবসময় বর্তমান পরিমাণ দেখায়।",
    "Recent Transactions": "সাম্প্রতিক লেনদেন", "Wallet Demo": "ডেমো ওয়ালেট", "Everyday payments, together": "প্রতিদিনের সব পেমেন্ট একসাথে",
    "Review every payment, download receipts and plan the next two months from your Report.": "প্রতিটি পেমেন্ট দেখুন, রসিদ ডাউনলোড করুন এবং পরবর্তী দুই মাসের পরিকল্পনা করুন।",
    "Review Report": "রিপোর্ট দেখুন", "Wallet": "ওয়ালেট", "Wallet transaction": "ওয়ালেট লেনদেন", "Wallet summary": "ওয়ালেটের সারসংক্ষেপ",
    "Amount": "পরিমাণ", "Amount (BDT)": "পরিমাণ (টাকা)", "Amount (৳)": "পরিমাণ (৳)", "Fee": "ফি", "Total deduction": "মোট কর্তন",
    "Remaining balance": "অবশিষ্ট ব্যালেন্স", "Available balance": "ব্যবহারযোগ্য ব্যালেন্স", "Balance after cash out": "ক্যাশ আউটের পর ব্যালেন্স",
    "Recipient": "প্রাপক", "Recipient mobile number": "প্রাপকের মোবাইল নম্বর", "Recipient Mobile": "প্রাপকের মোবাইল",
    "Recipient name": "প্রাপকের নাম", "Agent Number": "এজেন্ট নম্বর", "Agent number": "এজেন্ট নম্বর", "Agent": "এজেন্ট", "ATM": "এটিএম",
    "Agent cash out": "এজেন্ট ক্যাশ আউট", "ATM cash out": "এটিএম ক্যাশ আউট", "Cash-out channel": "ক্যাশ আউটের মাধ্যম",
    "Choose an ATM": "এটিএম বাছুন", "ATM location": "এটিএমের অবস্থান", "ATM provider": "এটিএম সেবাদাতা", "ATM withdrawal": "এটিএম থেকে উত্তোলন",
    "Confirm Cash Out": "ক্যাশ আউট নিশ্চিত করুন", "Cash out": "ক্যাশ আউট", "Cash Out Amount": "ক্যাশ আউটের পরিমাণ",
    "Bank transfer": "ব্যাংকে ট্রান্সফার", "Visa card": "ভিসা কার্ড", "Visa transfer": "ভিসায় ট্রান্সফার", "Bank": "ব্যাংক",
    "Bank Account": "ব্যাংক অ্যাকাউন্ট", "Bank account": "ব্যাংক অ্যাকাউন্ট", "Bank account number": "ব্যাংক অ্যাকাউন্ট নম্বর",
    "Account holder name": "অ্যাকাউন্টধারীর নাম", "Recipient name (demo)": "প্রাপকের নাম (ডেমো)", "Transfer rail": "ট্রান্সফারের পদ্ধতি",
    "Transfer method": "ট্রান্সফারের পদ্ধতি", "Transfer to bank": "ব্যাংকে ট্রান্সফার", "Transfer to Visa": "ভিসায় ট্রান্সফার",
    "Confirm Transfer": "ট্রান্সফার নিশ্চিত করুন", "Send money": "টাকা পাঠান", "Note (optional)": "নোট (ঐচ্ছিক)",
    "Source": "উৎস", "Add Money Source": "টাকা যোগ করার উৎস", "Card": "কার্ড", "Debit Card": "ডেবিট কার্ড",
    "Mobile Recharge": "মোবাইল রিচার্জ", "Recharge": "রিচার্জ", "Mobile Number": "মোবাইল নম্বর", "Mobile number": "মোবাইল নম্বর",
    "Operator": "অপারেটর", "Recharge Type": "রিচার্জের ধরন", "Prepaid": "প্রিপেইড", "Postpaid": "পোস্টপেইড",
    "Recharge Now": "এখন রিচার্জ করুন", "Pay Bill": "বিল দিন", "Bill Payment": "বিল পেমেন্ট", "Bill Category": "বিলের বিভাগ",
    "Bill type": "বিলের ধরন", "Provider": "সেবাদাতা", "Select provider": "সেবাদাতা বাছুন", "Choose a provider": "সেবাদাতা বাছুন",
    "Select a provider": "সেবাদাতা বাছুন", "Update Category": "বিভাগ বদলান", "Account / Meter Number": "অ্যাকাউন্ট / মিটার নম্বর",
    "Account / Reference Number": "অ্যাকাউন্ট / রেফারেন্স নম্বর", "Payment reference": "পেমেন্ট রেফারেন্স", "Pay Now": "এখন পেমেন্ট করুন",
    "Electricity": "বিদ্যুৎ", "Electricity Bill": "বিদ্যুৎ বিল", "Gas": "গ্যাস", "Gas Bill": "গ্যাস বিল", "Water": "পানি", "Water Bill": "পানির বিল",
    "Internet": "ইন্টারনেট", "Internet Bill": "ইন্টারনেট বিল", "TV": "টিভি", "TV Bill": "টিভি বিল", "Television": "টেলিভিশন",
    "Education": "শিক্ষা", "Education Fees": "শিক্ষা ফি", "School": "স্কুল", "College": "কলেজ", "University": "বিশ্ববিদ্যালয়",
    "School Fees": "স্কুল ফি", "College Fees": "কলেজ ফি", "University Fees": "বিশ্ববিদ্যালয় ফি", "Institution": "শিক্ষাপ্রতিষ্ঠান",
    "Insurance": "বিমা", "Insurance Premium": "বিমার প্রিমিয়াম", "Donation": "অনুদান", "Ticket": "টিকিট", "Hotel": "হোটেল",
    "Government": "সরকারি সেবা", "Government Fees": "সরকারি ফি", "Traffic Fine": "ট্রাফিক জরিমানা", "Toll": "টোল", "Credit Card": "ক্রেডিট কার্ড",
    "Savings Plan": "সঞ্চয় পরিকল্পনা", "Savings": "সঞ্চয়", "Savings calculator": "সঞ্চয় ক্যালকুলেটর", "Target Amount": "লক্ষ্যের পরিমাণ",
    "Monthly Contribution": "মাসিক জমা", "Monthly contribution": "মাসিক জমা", "Monthly contribution (BDT)": "মাসিক জমা (টাকা)",
    "Tenure": "মেয়াদ", "Tenure (months)": "মেয়াদ (মাস)", "Duration (months)": "মেয়াদ (মাস)", "Months": "মাস", "Start date": "শুরুর তারিখ",
    "Calculate": "হিসাব করুন", "Calculate Plan": "পরিকল্পনার হিসাব করুন", "Create Savings Plan": "সঞ্চয় পরিকল্পনা তৈরি করুন",
    "Save plan": "পরিকল্পনা সংরক্ষণ করুন", "Save Plan": "পরিকল্পনা সংরক্ষণ করুন", "Your savings plans": "আপনার সঞ্চয় পরিকল্পনা",
    "Projected return": "সম্ভাব্য মুনাফা", "Estimated return": "আনুমানিক মুনাফা", "Estimated maturity": "মেয়াদ শেষে আনুমানিক পরিমাণ",
    "Maturity date": "মেয়াদ শেষের তারিখ", "Total contribution": "মোট জমা", "Total principal": "মোট মূলধন",
    "Annual rate": "বার্ষিক হার", "Pay Later": "পরে পরিশোধ", "Credit limit": "ঋণের সীমা", "Available credit": "ব্যবহারযোগ্য ঋণ",
    "Outstanding": "বকেয়া", "Outstanding balance": "বকেয়া পরিমাণ", "Due date": "পরিশোধের তারিখ", "Repay": "পরিশোধ করুন",
    "Repayment": "ঋণ পরিশোধ", "Repay now": "এখন পরিশোধ করুন", "Your Pay Later plans": "আপনার পরে পরিশোধের পরিকল্পনা",
    "Request Money": "টাকা অনুরোধ করুন", "Prepare Request": "অনুরোধ তৈরি করুন", "Copy message": "বার্তা কপি করুন",
    "Clear request": "অনুরোধ মুছুন", "Prepared request": "প্রস্তুত অনুরোধ", "Note": "নোট", "Message": "বার্তা",
    "Account": "অ্যাকাউন্ট", "Personal information": "ব্যক্তিগত তথ্য", "Make it yours": "নিজের মতো সাজান",
    "Your personal details, picture and account preferences.": "আপনার ব্যক্তিগত তথ্য, ছবি ও অ্যাকাউন্টের পছন্দ।",
    "Full Name": "পুরো নাম", "Nickname": "ডাকনাম", "Email": "ইমেইল", "Address": "ঠিকানা", "Member since": "সদস্য হয়েছেন",
    "Profile picture": "প্রোফাইল ছবি", "Your profile picture": "আপনার প্রোফাইল ছবি", "Save Changes": "পরিবর্তন সংরক্ষণ করুন",
    "Remove current picture": "বর্তমান ছবি সরান", "This number identifies your wallet account.": "এই নম্বর আপনার ওয়ালেট অ্যাকাউন্টের পরিচয়।",
    "What should we call you?": "আপনাকে কী নামে ডাকব?", "Street, area, city and postal code": "রাস্তা, এলাকা, শহর ও পোস্ট কোড",
    "✓ Verified Account": "✓ যাচাইকৃত অ্যাকাউন্ট", "Verification pending": "যাচাই বাকি আছে", "Photo size": "ছবির আকার",
    "Fit image": "পুরো ছবি রাখুন", "Square crop": "বর্গাকারে কাটুন", "Resize & crop": "আকার ও কাটছাঁট",
    "Preview": "প্রিভিউ", "Settings": "সেটিংস", "Language": "ভাষা", "Appearance": "থিম", "Light": "হালকা", "Dark": "গাঢ়", "System": "সিস্টেম",
    "English": "English", "বাংলা": "বাংলা", "Save": "সংরক্ষণ", "Search": "খুঁজুন", "Search services, bills, etc.": "সেবা, বিল ও লেনদেন খুঁজুন",
    "Search services and transactions": "সেবা ও লেনদেন খুঁজুন", "Transaction": "লেনদেন", "Transaction ID": "লেনদেন আইডি",
    "Transaction reference": "লেনদেনের রেফারেন্স", "Invoice": "ইনভয়েস", "Invoice number": "ইনভয়েস নম্বর", "Reference": "রেফারেন্স",
    "Date": "তারিখ", "Time": "সময়", "Type": "ধরন", "Direction": "দিক", "Status": "অবস্থা", "Counterparty": "অপর পক্ষ",
    "Success": "সফল", "Successful": "সফল", "Pending": "অপেক্ষমান", "Failed": "ব্যর্থ", "Cancelled": "বাতিল", "Scheduled": "নির্ধারিত", "Completed": "সম্পন্ন",
    "All": "সব", "All types": "সব ধরন", "All statuses": "সব অবস্থা", "Incoming": "আসা টাকা", "Outgoing": "যাওয়া টাকা",
    "Money in": "আসা টাকা", "Money out": "যাওয়া টাকা", "End date": "শেষের তারিখ", "Date range": "তারিখের সীমা",
    "Filter": "ফিল্টার", "Filters": "ফিল্টার", "Reset": "রিসেট", "Export": "এক্সপোর্ট", "Export Report": "রিপোর্ট এক্সপোর্ট",
    "Download": "ডাউনলোড", "Download PDF": "পিডিএফ ডাউনলোড", "Download JPG": "জেপিজি ডাউনলোড", "Format": "ফরম্যাট",
    "Print / Receipt": "প্রিন্ট / রসিদ", "Receipt": "রসিদ", "Transaction receipt": "লেনদেনের রসিদ", "Transaction Receipt": "লেনদেনের রসিদ",
    "Previous": "আগের", "Next": "পরের", "Total": "মোট", "Total fees": "মোট ফি", "Wallet change": "ব্যালেন্সের পরিবর্তন",
    "Report insights": "রিপোর্টের বিশ্লেষণ", "Spending by category": "বিভাগ অনুযায়ী খরচ", "Cumulative cash flow": "ক্রমবর্ধমান নগদ প্রবাহ",
    "Spending share": "খরচের ভাগ", "Cumulative histogram": "ক্রমবর্ধমান হিস্টোগ্রাম", "Bar chart": "বার চার্ট", "Pie chart": "পাই চার্ট",
    "App Assistant": "অ্যাপ সহকারী", "Your wallet guide": "আপনার ওয়ালেট সহকারী", "Local app guide": "স্থানীয় অ্যাপ সহকারী",
    "AI app assistant": "এআই অ্যাপ সহকারী", "App guide": "অ্যাপ সহকারী", "Demo wallet": "ডেমো ওয়ালেট", "You": "আপনি",
    "Send": "পাঠান", "Sending...": "পাঠানো হচ্ছে…", "Clear chat": "চ্যাট মুছুন", "Chat cleared.": "চ্যাট মুছে গেছে।",
    "Ask about your wallet or this app...": "আপনার ওয়ালেট বা এই অ্যাপ সম্পর্কে জিজ্ঞাসা করুন…",
    "Question about this app": "এই অ্যাপ সম্পর্কে প্রশ্ন", "Spending insights": "খরচের বিশ্লেষণ", "Plan Auto Pay": "অটো পে পরিকল্পনা",
    "Guidance only. Confirm payments in the app.": "সহকারী পরামর্শ দেয়। পেমেন্ট অ্যাপে নিশ্চিত করুন।",
    "I can help you understand spending, check recipients, plan Auto Pay and download reports. All balances and activity in this prototype are demo data.": "আমি আপনার খরচ বুঝতে, প্রাপক যাচাই করতে, অটো পে পরিকল্পনা করতে ও রিপোর্ট ডাউনলোড করতে সাহায্য করতে পারি। এই অ্যাপের সব ব্যালেন্স ও লেনদেন ডেমো তথ্য।",
    "Uses app guidance and your wallet totals. Free-form AI answers need a configured provider.": "আপনার ওয়ালেটের হিসাব ও অ্যাপের তথ্য দিয়ে উত্তর দেয়। পূর্ণ এআই উত্তরের জন্য provider সেট করতে হবে।",
    "Reading your app information...": "আপনার অ্যাপের তথ্য দেখা হচ্ছে…", "Checking recipient...": "প্রাপক যাচাই করা হচ্ছে…",
    "Blocked number. This recipient cannot transact.": "ব্লক করা নম্বর। এই প্রাপকের সঙ্গে লেনদেন করা যাবে না।",
    "Not registered. No verified name exists in this project directory.": "নিবন্ধিত নয়। এই অ্যাপের তালিকায় যাচাইকৃত নাম নেই।",
    "Recipient check is unavailable. Check your connection; the server will validate when you submit.": "প্রাপক যাচাই এখন সম্ভব নয়। সংযোগ পরীক্ষা করুন; জমা দেওয়ার সময় সার্ভার যাচাই করবে।",
    "QR payment instructions": "কিউআর পেমেন্ট নির্দেশনা", "Generate QR": "কিউআর তৈরি করুন", "Read QR": "কিউআর পড়ুন",
    "Read QR image": "কিউআর ছবি পড়ুন", "Or paste UpayX QR text": "অথবা UpayX কিউআর টেক্সট পেস্ট করুন",
    "Demo operation QR code": "ডেমো লেনদেনের কিউআর কোড",
    "Generate or read a demo QR to fill this form. Review the recipient, amount and fee before confirming. Codes expire after 15 minutes.": "ফর্ম পূরণ করতে ডেমো কিউআর তৈরি করুন বা পড়ুন। নিশ্চিত করার আগে প্রাপক, পরিমাণ ও ফি দেখুন। কোড ১৫ মিনিট পর মেয়াদোত্তীর্ণ হয়।",
    "QR only prepares the form; it never moves money.": "কিউআর শুধু ফর্ম পূরণ করে; নিজে টাকা পাঠায় না।",
    "Form filled. Review all details before confirming.": "ফর্ম পূরণ হয়েছে। নিশ্চিত করার আগে সব তথ্য দেখুন।",
    "This browser cannot read QR images. Paste the UpayX QR text instead.": "এই ব্রাউজারে কিউআর ছবি পড়া যাচ্ছে না। UpayX কিউআর টেক্সট পেস্ট করুন।",
    "No QR code found in this image.": "এই ছবিতে কিউআর কোড পাওয়া যায়নি।", "Welcome back!": "আবার স্বাগতম!",
    "Profile updated.": "প্রোফাইল আপডেট হয়েছে।", "Money sent successfully.": "সফলভাবে টাকা পাঠানো হয়েছে।",
    "Money added successfully.": "সফলভাবে টাকা যোগ হয়েছে।", "Cash-out completed successfully.": "ক্যাশ আউট সফল হয়েছে।",
    "Transaction notifications marked as read.": "লেনদেনের নোটিফিকেশন পড়া হয়েছে।", "Notification preferences saved.": "নোটিফিকেশন পছন্দ সংরক্ষিত হয়েছে।",
    "Hackathon Prototype": "হ্যাকাথন প্রোটোটাইপ", "Bangladesh time": "বাংলাদেশ সময়", "BD": "বাংলাদেশ",
    "Log in": "লগ ইন", "Login": "লগ ইন", "Sign in": "সাইন ইন", "Create Account": "অ্যাকাউন্ট তৈরি করুন",
    "Continue": "চালিয়ে যান", "Verify OTP": "ওটিপি যাচাই করুন", "OTP": "ওটিপি", "Demo OTP": "ডেমো ওটিপি",
}

from app.services.localization_extra import EXTRA_BANGLA
from app.services.localization_wallet import WALLET_BANGLA
from app.services.localization_assistant import ASSISTANT_BANGLA
from app.services.localization_insights import INSIGHTS_BANGLA
BANGLA.update(EXTRA_BANGLA)
BANGLA.update(WALLET_BANGLA)
BANGLA.update(ASSISTANT_BANGLA)
BANGLA.update(INSIGHTS_BANGLA)
BANGLA.update({
    "bill": "বিল", "bills": "বিল", "payment": "পেমেন্ট", "bank": "ব্যাংক", "card": "কার্ড", "wallet": "ওয়ালেট",
    "Grameenphone": "গ্রামীণফোন", "Robi": "রবি", "Airtel": "এয়ারটেল", "Banglalink": "বাংলালিংক", "Teletalk": "টেলিটক",
    "Titas Gas": "তিতাস গ্যাস", "Bakhrabad Gas": "বাখরাবাদ গ্যাস", "Jalalabad Gas": "জালালাবাদ গ্যাস",
    "Karnaphuli Gas": "কর্ণফুলী গ্যাস", "Pashchimanchal Gas": "পশ্চিমাঞ্চল গ্যাস", "Sundarban Gas": "সুন্দরবন গ্যাস",
    "Omera LPG": "ওমেরা এলপিজি", "Bashundhara LPG": "বসুন্ধরা এলপিজি", "DESCO Electricity": "ডেসকো বিদ্যুৎ", "DPDC Electricity": "ডিপিডিসি বিদ্যুৎ",
    "Unable to load chat. Refresh and try again.": "চ্যাট আনা যায়নি। পেজ রিফ্রেশ করে আবার চেষ্টা করুন।",
    "QR amount must be between 0.01 and 100,000, with up to two decimal places.": "কিউআরের পরিমাণ ০.০১ থেকে ১,০০,০০০ টাকা এবং দশমিকের পর সর্বোচ্চ দুই অঙ্ক হতে হবে।",
    "Enter a valid QR amount.": "কিউআরের সঠিক পরিমাণ লিখুন।", "This request account no longer exists.": "এই অনুরোধের অ্যাকাউন্টটি আর নেই।",
    "Crop mode": "কাটছাঁটের ধরন", "Horizontal position": "ডানে-বামে অবস্থান", "Vertical position": "উপরে-নিচে অবস্থান",
    "JPG, PNG, WebP, GIF, BMP, TIFF, ICO, AVIF, HEIC, JPEG2000, QOI, PSD, TGA and PPM · Up to 5 MB. Animated images use their first frame.": "JPG, PNG, WebP, GIF, BMP, TIFF, ICO, AVIF, HEIC, JPEG2000, QOI, PSD, TGA ও PPM · সর্বোচ্চ ৫ মেগাবাইট। চলমান ছবির প্রথম ফ্রেম ব্যবহার করা হয়।",
    "Choose valid image resize and crop settings.": "ছবির আকার ও কাটছাঁটের সঠিক সেটিংস বাছুন।",
    "Preview unavailable in this browser. The server will decode supported formats when you save.": "এই ব্রাউজারে প্রিভিউ দেখা যাচ্ছে না। সংরক্ষণের সময় সার্ভার সমর্থিত ছবি খুলবে।",
    "Choose an image under 5 MB.": "৫ মেগাবাইটের কম একটি ছবি বাছুন।", "Choose a valid QR image.": "সঠিক কিউআর ছবি বাছুন।",
    "Choose a QR image.": "কিউআর ছবি বাছুন।", "Enter valid details and generate a new QR.": "সঠিক তথ্য দিয়ে নতুন কিউআর তৈরি করুন।",
    "Use a QR code for this operation.": "এই সেবার কিউআর কোড ব্যবহার করুন।",
    "Choose the matching channel before reading this QR.": "কিউআর পড়ার আগে সঠিক মাধ্যম বাছুন।",
    "QR provider does not match the selected category.": "কিউআরের সেবাদাতা নির্বাচিত বিভাগের সঙ্গে মিলছে না।",
    "Use a signed UpayX demo QR code.": "স্বাক্ষর করা UpayX ডেমো কিউআর কোড ব্যবহার করুন।",
    "This QR code is invalid or expired. Generate a new code.": "কিউআরটি ভুল বা মেয়াদোত্তীর্ণ। নতুন কোড তৈরি করুন।",
    "This QR code belongs to another account or operation.": "কিউআরটি অন্য অ্যাকাউন্ট বা সেবার।",
    "Unable to clear chat. Refresh and try again.": "চ্যাট মোছা যায়নি। পেজ রিফ্রেশ করে আবার চেষ্টা করুন।",
})


def translate(text, language="bn"):
    if language != "bn" or not isinstance(text, str):
        return text
    stripped = text.strip()
    if stripped in BANGLA:
        return text.replace(stripped, BANGLA[stripped], 1)
    # Localize only known UI structures, never arbitrary fragments of user names or notes.
    for prefix, replacement in (("Back to ", "ফিরে যান: "), ("Welcome, ", "স্বাগতম, "),
                                ("Recent Transactions · ", "সাম্প্রতিক লেনদেন · ")):
        if stripped.startswith(prefix):
            return text.replace(stripped, replacement + translate(stripped[len(prefix):]), 1)
    match = re.fullmatch(r"(Mark all as read) \((\d+)\)", stripped)
    if match:
        return f"{BANGLA[match[1]]} ({match[2]})"
    match = re.fullmatch(r"Last (\d+) days(?: activity)?", stripped)
    if match:
        return f"গত {match[1]} দিনের কার্যক্রম"
    match = re.fullmatch(r"Last (\d+) days (Transactions|Payments|Money Out)", stripped)
    if match:
        return f"গত {match[1]} দিনের {translate(match[2])}"
    match = re.fullmatch(r"(.+) summary", stripped)
    if match and match[1] in BANGLA:
        return f"{BANGLA[match[1]]} সারসংক্ষেপ"
    match = re.fullmatch(r"For (.+) · ৳ (.+)", stripped)
    if match:
        return f"প্রাপক: {match[1]} · ৳ {match[2]}"
    match = re.fullmatch(r"Page (\d+) of (\d+)", stripped)
    if match:
        return f"{match[2]} পাতার মধ্যে {match[1]}"
    match = re.fullmatch(r"(\d+) (months|installments|installment)", stripped)
    if match:
        return f"{match[1]} {'মাস' if match[2] == 'months' else 'কিস্তি'}"
    match = re.fullmatch(r"Welcome to (.+)", stripped)
    if match:
        return f"{match[1]}-এ স্বাগতম"
    match = re.fullmatch(r"(.+) Payment", stripped)
    if match and match[1] in BANGLA:
        return f"{BANGLA[match[1]]} পেমেন্ট"
    for sep in (" · ", " | ", " →", ": "):
        if sep in stripped:
            return text.replace(stripped, sep.join(translate(part) for part in stripped.split(sep)), 1)
    return text


class _Translator(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        protected = 2 if tag in {"script", "style"} else (1 if tag in {"textarea", "code"} or any(k == "data-user-content" for k, v in attrs) else 0)
        raw = self.get_starttag_text()
        if not any(self.stack):
            for key, value in attrs:
                if key in {"placeholder", "aria-label", "title", "alt"} and value:
                    raw = re.sub(rf'({key}\s*=\s*)([\"\x27])(.*?)\2',
                                 lambda m: m[1] + m[2] + escape(translate(value), quote=True) + m[2], raw, count=1)
        self.output.append(raw)
        if tag not in {"input", "meta", "link", "img", "br", "hr", "source", "area", "base", "embed", "wbr"}:
            self.stack.append(max(protected, max(self.stack, default=0)))

    def handle_startendtag(self, tag, attrs):
        self.output.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        self.output.append(f"</{tag}>")
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        self.output.append(data if 2 in self.stack else escape(data if any(self.stack) else translate(data), quote=False))

    def handle_entityref(self, name):
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        self.output.append(f"&#{name};")

    def handle_decl(self, decl):
        self.output.append(f"<!{decl}>")

    def handle_comment(self, data):
        self.output.append(f"<!--{data}-->")


def translate_html(html):
    parser = _Translator()
    parser.feed(html)
    return "".join(parser.output)
