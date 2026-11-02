"""Sentences read aloud to build the profile.

Written for this app. Each one leans on sounds that many non-native speakers
find hard (th, w and v, r and l, short and long vowels, word endings), in the
kind of language people use in talks and interviews.
"""

SENTENCES = {
    "s01": "Thank you all for coming, I think this will be worth your time.",
    "s02": "The weather was worse than we thought, so the event moved inside.",
    "s03": "We value every voice in the team, whether it is loud or quiet.",
    "s04": "Our revenue grew steadily while the wider market stayed flat.",
    "s05": "I would like to walk you through the three main findings.",
    "s06": "Please leave the sheet on the seat next to the window.",
    "s07": "The bad news is that the bed in the hotel was broken.",
    "s08": "She asked whether the results were reliable enough to publish.",
    "s09": "The research shows a clear rise in remote work across the region.",
    "s10": "We will review the leadership role later in the year.",
    "s11": "This method is faster, though it needs more memory at the start.",
    "s12": "Let me briefly summarise the strengths and weaknesses of each approach.",
    "s13": "The vision for this project is simple: build something people use.",
    "s14": "We measured the pleasure of using the app in an unusual way.",
    "s15": "Writing clear documentation is worth the effort in the long run.",
    "s16": "I believe the evidence supports a different conclusion entirely.",
    "s17": "Their feedback was thoughtful, and they raised several valid points.",
    "s18": "The working group will meet again on Thursday to discuss the budget.",
    "s19": "Thousands of visitors travelled north to watch the festival.",
    "s20": "My background is in software development and data analysis.",
    "s21": "I enjoy solving difficult problems with a small, focused team.",
    "s22": "The first version was rough, but the feedback helped us improve it.",
    "s23": "Customers wanted a cheaper option without losing any features.",
    "s24": "We tested the theory with a full sample of real users.",
    "s25": "Throughout the year the company worked on its growth strategy.",
    "s26": "Developers should think carefully about security from the very beginning.",
    "s27": "The pull request was approved after a short and useful review.",
    "s28": "Our goal is to reduce waiting times without hiring extra staff.",
    "s29": "It is important to listen, especially when people disagree with you.",
    "s30": "The model learned to recognise words from thousands of recordings.",
    "s31": "We should leave room in the schedule for unexpected problems.",
    "s32": "This chart compares our three products over the whole period.",
    "s33": "The system sends a warning when the server load is too high.",
    "s34": "I worked with clients in several countries during my placement.",
    "s35": "Teamwork matters more than individual brilliance in most projects.",
    "s36": "Nothing is finished until the users are happy with the result.",
    "s37": "Each week we share what went well and what we would change.",
    "s38": "The vehicle was delivered on time, with everything in working order.",
    "s39": "Good communication builds trust between engineers and managers.",
    "s40": "Finally, thank you for listening, and I am happy to take questions.",
}

PROFILE_TARGET = 30  # sentences before the profile is considered complete


def next_sentence(read_counts):
    """The sentence read the fewest times, in order. `read_counts` maps key -> times read."""
    return min(SENTENCES, key=lambda key: (read_counts.get(key, 0), key))
