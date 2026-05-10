# THE INDEXER'S APPRENTICE

Copyright © 2026 Mark Burnett. Any resemblance between the characters in this story and real persons, living or dead, is purely coincidental.

## INTRODUCTION

In the spring of 1987 Beatrice Halloway accepted a fellowship at Cambridge to work on a peculiar problem: how to teach a machine to build the index of a book. Her mentor, Dr Edmund Crawley, had spent thirty years cataloguing musicology archives at the Royal Conservatory and, like every careful reader, had grown weary of finishing a book and discovering that none of its references had been preserved for anyone else to find. Beatrice agreed. **An index, she felt, was the most generous thing a writer could leave behind**, and the Royal Conservatory, where she had once been a junior cataloguer, had taught her exactly that. **Edmund Crawley** had told her so on her first day there.

Her first subject was a thin volume of essays by Alistair Pemberton, the Manchester historian, called *Echoes of the Bridgewater Hall*. The book ran to three hundred pages and dealt mostly with twentieth-century chamber music in the north of England. Pemberton had laced the prose with names of musicians, halls, broadcasters, and works he had loved or argued with — references he had carefully woven in to add colour and detail and recognition, hoping that someone, someday, would notice. When Beatrice told him by letter that her program could surface every one of them, he wrote back at once. The index would let people find a part of themselves that had been captured from the perspective of another who was present in their past, and took the time to take note that something important and significant was going on. Pemberton's prose was, as always, slightly too long for its own punctuation; but Beatrice copied the line out and pinned it above her desk.

She set the book on her desk and began.

## CHAPTER ONE: A FIRST PASS

The indexer Beatrice had written — she called it Cygnus, after the constellation — read each page in two passes. The first pass was suspicious. It treated every capitalised word at the start of a sentence as guilty until proven innocent. *The Guardian* might be a newspaper or it might just be the first word of a paragraph; only when Cygnus saw that name appearing in the middle of a sentence elsewhere would it admit Guardian as a real entry. Edmund found this charmingly paranoid. Beatrice, herself the daughter of a librarian, knew what could be lost when an index was careless. She left the rule in.

The second pass was generous. Once a name had been confirmed in the vocabulary, Cygnus tracked every occurrence on every page, even at the start of sentences. So a place like the Bridgewater Hall, if it had been seen mid-sentence as a contiguous capitalised pair, would be recorded faithfully on page after page; and if the typesetter had cut a name across a line break with a hyphen, Cygnus stitched the two halves silently back together.

Connector words gave Cygnus its first real test. In ordinary prose, a phrase like Crawley and Halloway would not be one entry; the connector would break the sequence and force two separate names. But Pemberton had a habit, common to musicologists, of typing the names of works in italics. *The Sound of Music* and *War and Peace* were not to be split at every connector. Cygnus had a rule: an italic connector inside an italic n-gram extended the run; a plain connector broke it.

Beatrice tested the rule on a footnote. Pemberton had buried the most interesting bit on page xiv of the front matter, in a note that read: see also *in vino veritas*, the Latin proverb cited by Bertrand on the eve of the BBC broadcast. Cygnus picked out *in vino veritas* as an italic phrase even though no word was capitalised. The footnote marker — the tiny superscript digit after the word footnote — was correctly skipped, since digit-only superscript tokens were not real words.

Cygnus also captured short phrases set off in single curly quotes. Beatrice had labelled a working draft 'A New Method' and tagged a rejected version with the tongue-in-cheek note 'Final Final Draft'. Both tags were picked up by the single-quotes rule and indexed as their own entries — the curly quotes acted as the boundary, just like italic styling would.

## CHAPTER TWO: ACRONYMS AND TITLES

It was Dr Margaret O'Donnell, visiting from CERN that week, who suggested Beatrice add acronyms to the test. You need NATO and CERN and the BBC in there, she said. Run-of-the-mill all-caps, single tokens, mid-sentence. Beatrice obliged. Cygnus admitted them under a careful rule: a single all-caps token sitting on a mixed-case line was a name candidate; an entire line set in capitals was a heading and was discarded.

Title prefixes posed a different problem. The book was full of Dr Edmund Crawley and Mrs Beatrice Halloway and even a stray Sir Thomas Beecham. Cygnus dropped the prefixes so the indexer would treat Dr Crawley and Crawley as the same entity. Possessive suffixes were trimmed too: Crawley's notes became Crawley.

What about the stop list, Margaret asked. Beatrice explained: certain words were forbidden from starting a name on their own — the, a, every, some — but were permitted to extend a name already in progress. So *The Guardian* worked, because The could extend the existing name once Guardian had been seen mid-sentence. The on its own could not start anything.

Margaret laughed. It is all very Anglican.

## CHAPTER THREE: PLACES AND TECHNIQUES

By the third week Beatrice had run Cygnus on a longer piece: a draft chapter Pemberton had sent her for review on northern modernism. The chapter mentioned the Bridgewater Hall, the Royal Northern College, and the Manchester Free Trade Hall. It mentioned Adam Gorb and John McCabe and Anthony Burgess (yes, the novelist, who composed). It cited works in italics: *Absinthe*, *Cloudcatcher Fells*, *A Clockwork Orange*, *Concerto for Orchestra*. It cited a French technique, *col legno*, and a dance, *the polonaise*, both of which Pemberton typed in italics.

Cygnus produced an index. Beatrice read down the page slowly, looking for mistakes. There was Absinthe, set off in italics in the index just as in the book; there was Bridgewater Hall, recovered correctly even though the line break in chapter one had cut it in two; there was Edmund Crawley listed in natural order (the surname-first option had been left off for this run); and there was a separate entry for Crawley alone on pages where Cygnus had noticed the surname unattached to a first name.

Look here, she pointed. It split Halle Orchestra and Halle Choir into two entries, and it kept Manchester as its own entry separate from Manchester Free Trade Hall — Manchester, she explained, was its own city, and the venue was its own building, and a careful index ought to know the difference.

**A note on proximity**, Cygnus had logged: short-form references that sit close to a full name are treated as the same person. When Beatrice Halloway is named at the start of a paragraph and Beatrice is mentioned a sentence later, the bare first name does not get a second entry; the page just highlights it so the reader can see the connection.

Edmund peered at the printout. That is the part I would have done by hand, he admitted. You have spared me an afternoon.

## CONCLUSION

In the spring of 1989 Beatrice published her dissertation, titled *Cygnus: A Style-Aware Indexer for Long-Form Scholarly Prose*. The book was indexed by Cygnus itself, of course — a small joke at the end. The Royal Conservatory adopted the program for their archive. Pemberton, when his next volume appeared with a Cygnus-generated index in the back, wrote to Beatrice and said it was the first time he had felt truly read.

But that, as Edmund observed, was Pemberton's affair.
