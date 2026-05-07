# THE INDEXER'S APPRENTICE

## INTRODUCTION

In the spring of 1987 Beatrice Halloway accepted a fellowship at Cambridge to work on a peculiar problem: how to teach a machine to build the index of a book. Her mentor, Dr Edmund Crawley, had spent thirty years cataloguing musicology archives at the Royal Conservatory and was sceptical that any program could replace a careful human reader. "Indexing is taste," he liked to say, "not arithmetic." Beatrice disagreed, but politely.

Her first subject was a thin volume of essays by Alistair Pemberton, the Manchester historian, called *Echoes of the Bridgewater Hall*. The book ran to three hundred pages and dealt mostly with twentieth-century chamber music in the north of England. Pemberton's prose was dense, his footnotes copious, and his refusal to use indexes himself almost a point of pride. Pemberton would say, Edmund warned her, that an index is a confession of failure on the part of the writer.

She set the book on her desk and began.

## CHAPTER ONE: A FIRST PASS

The indexer Beatrice had written — she called it Cygnus, after the constellation — read each page in two passes. The first pass was suspicious. It treated every capitalised word at the start of a sentence as guilty until proven innocent. *The Guardian* might be a newspaper or it might just be the first word of a paragraph; only when Cygnus saw that name appearing in the middle of a sentence elsewhere would it admit Guardian as a real entry. Edmund found this charmingly paranoid.

The second pass was generous. Once a name had been confirmed in the vocabulary, Cygnus tracked every occurrence on every page, even at the start of sentences. So a place like the Bridgewater Hall, if it had been seen mid-sentence as a contiguous capitalised pair, would be recorded faithfully on page after page; and if the typesetter had cut a name across a line break with a hyphen, Cygnus stitched the two halves silently back together.

Connector words gave Cygnus its first real test. In ordinary prose, a phrase like Crawley and Halloway would not be one entry; the connector would break the sequence and force two separate names. But Pemberton had a habit, common to musicologists, of typing the names of works in italics. *The Sound of Music* and *War and Peace* were not to be split at every connector. Cygnus had a rule: an italic connector inside an italic n-gram extended the run; a plain connector broke it.

She tested the rule on a footnote. Pemberton, true to form, had buried the most interesting bit on page xiv of the front matter, in a note that read: see also *in vino veritas*, the Latin proverb cited by Bertrand on the eve of the BBC broadcast. Cygnus picked out *in vino veritas* as an italic phrase even though no word was capitalised. The footnote marker — the tiny superscript digit after the word footnote — was correctly skipped, since digit-only superscript tokens were not real words.

## CHAPTER TWO: ACRONYMS AND TITLES

It was Dr Margaret O'Donnell, visiting from CERN that week, who suggested Beatrice add acronyms to the test. You need NATO and CERN and the BBC in there, she said. Run-of-the-mill all-caps, single tokens, mid-sentence. Beatrice obliged. Cygnus admitted them under a careful rule: a single all-caps token sitting on a mixed-case line was a name candidate; an entire line set in capitals was a heading and was discarded.

Title prefixes posed a different problem. The book was full of Dr Edmund Crawley and Mrs Beatrice Halloway and even a stray Sir Thomas Beecham. Cygnus dropped the prefixes so the indexer would treat Dr Crawley and Crawley as the same entity. Possessive suffixes were trimmed too: Crawley's notes became Crawley.

What about the stop list, Margaret asked. Beatrice explained: certain words were forbidden from starting a name on their own — the, a, every, some — but were permitted to extend a name already in progress. So *The Guardian* worked, because The could extend the existing name once Guardian had been seen mid-sentence. The on its own could not start anything.

Margaret laughed. It is all very Anglican.

## CHAPTER THREE: PLACES AND TECHNIQUES

By the third week Beatrice had run Cygnus on a longer piece: a draft chapter Pemberton had sent her for review on northern modernism. The chapter mentioned the Bridgewater Hall, the Royal Northern College, and the Manchester Free Trade Hall. It mentioned Adam Gorb and John McCabe and Anthony Burgess (yes, the novelist, who composed). It cited works in italics: *Absinthe*, *Cloudcatcher Fells*, *A Clockwork Orange*, *Concerto for Orchestra*. It cited a French technique, *col legno*, and a dance, *the polonaise*, both of which Pemberton typed in italics.

Cygnus produced an index. Beatrice read down the page slowly, looking for mistakes. There was Absinthe, set off in italics in the index just as in the book; there was Bridgewater Hall, recovered correctly even though the line break in chapter one had cut it in two; there was Edmund Crawley listed in natural order (the surname-first option had been left off for this run); and there was a separate entry for Crawley alone on pages where Cygnus had noticed the surname unattached to a first name.

Look here, she pointed. It split Halle Orchestra and Halle Choir into two entries, and it kept Manchester as its own entry separate from Manchester Free Trade Hall. Cygnus refused to print a redundant entry only when every page of the standalone term was already covered.

Edmund peered at the printout. That is the part I would have done by hand, he admitted. You have spared me an afternoon.

## CONCLUSION

In the spring of 1989 Beatrice published her dissertation, titled *Cygnus: A Style-Aware Indexer for Long-Form Scholarly Prose*. The book was indexed by Cygnus itself, of course — a small joke at the end. The Royal Conservatory adopted the program for their archive. Pemberton, characteristically, refused to use it.

But that, as Edmund observed, was Pemberton's affair.
