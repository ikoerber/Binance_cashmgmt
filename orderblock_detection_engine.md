Dieses Markdown beschreibt ein weiteres eigenständiges Modul was als Ergänzung in die  vorhanden Service Applikation integriert werden soll.

⸻

Master-Spezifikation: Orderblock-Detection & Backtest-Engine (BTC/EUR, Binance Spot)

1. Projekt-Kontext & Qualitätsanspruch

Ziel: Identifikation hochreaktiver institutioneller Zonen (Orderblocks) auf BTC/EUR, Handelsplatz Binance Spot.

Qualitätsstandard:
	•	Clean-Code-Prinzipien
	•	Vollständige Testabdeckung (Unit & Integration)
	•	Iterative Entwicklung mit Review nach jedem Meilenstein
	•	Fokus auf mathematische Präzision, deterministische Regeln und Datenintegrität vor Visualisierung

Kernprinzip: Jede Detektions-Entscheidung muss aus historischen OHLCV-Daten zeitkonsistent herleitbar und reproduzierbar sein (kein Look-Ahead-Bias).

⸻

2. Begriffe & Normierungen (verbindlich)

2.1 Datenbasis
	•	Inputdaten: Historische OHLCV-Kerzen (Open, High, Low, Close, Volume) je Timeframe.
	•	Zeitstempel: ISO-8601 (UTC) im Output, interne Verarbeitung in eindeutiger Zeitskala.
	•	Symbol: BTC/EUR (Binance Spot).

2.2 Kerzen- und Preisregeln
	•	Preisberührung (Touch): Ein Preis gilt als in einer Zone gewesen, wenn der Kerzenbereich die Zone schneidet:
High >= ZoneBottom und Low <= ZoneTop.
	•	Wick vs Body: Wo nicht explizit anders definiert, gelten:
	•	BOS/MSS: Körper-Close-Kriterium (Close entscheidend, nicht Docht).
	•	Stop/Invalidierung im Backtest: “Stop Edge berührt” = Wick-Touch (konservativ und eindeutig).

2.3 Parameter (konfigurierbar, aber deterministisch)

Folgende Parameter sind Bestandteil einer Strategie-Konfiguration und werden im Report mitgeführt:
	•	atr_length (Default: 20)
	•	atr_multiplier für Displacement (Default: 2.5)
	•	fvg_window (Default: erste 3 Kerzen nach OB)
	•	swing_fractal_n (Default: 2)
	•	target_rr (Default: 2.0 * OB-Weite)
	•	entry_policy (Default: “Near-Edge Entry”)
	•	stop_policy (Default: “Stop Edge Touch” per Wick)
	•	mitigation_policy (Default: “Zone Touch”)

⸻

3. Modul A: Detection Engine (Erkennungs-Logik)

3.1 Definition eines validen Orderblocks (VALID_OB)

Ein Objekt wird nur dann als VALID_OB deklariert, wenn es die folgenden Phasen erfolgreich durchläuft und dabei zeitkonsistent (ohne Wissen über die Zukunft jenseits der jeweiligen Bestätigung) bleibt.

Phase 1: Formations-Check (Base)
Bullish OB (BULLISH_OB):
	•	Kandidat ist die letzte bearish Kerze (Close < Open), die unmittelbar vor einem nachfolgenden bullischen Impuls steht.

Bearish OB (BEARISH_OB):
	•	Kandidat ist die letzte bullish Kerze (Close > Open), die unmittelbar vor einem nachfolgenden bearischen Impuls steht.

Zone-Definition (verbindlich):
	•	Zone = [bottom, top] = [Low(OB-Kerze), High(OB-Kerze)]
	•	equilibrium = (top + bottom) / 2

Phase 2: Impuls-Check (Displacement)
Die auf den OB folgende Bewegung muss signifikanten Displacement zeigen.

ATR-Grundlage:
	•	ATR wird auf True Range berechnet, Länge atr_length.

Displacement-Kriterium (verbindlich, OHLCV-kompatibel):
	•	Innerhalb der ersten drei Kerzen nach der OB-Kerze muss mindestens eine Kerze eine Range besitzen von:
Range = High - Low >= atr_multiplier * ATR(ob_timestamp)
	•	Alternativ kann (falls explizit konfiguriert) ein Close-Diff-Kriterium genutzt werden; Standard ist Range-basiert.

Phase 3: Fair Value Gap-Check (FVG)
Es muss ein Fair Value Gap innerhalb der ersten fvg_window Kerzen nach dem OB entstehen.

FVG-Definition (3-Kerzen-Imbalance, verbindlich):
	•	Bullish FVG liegt vor, wenn für Kerze i gilt:
Low(i) > High(i-2)
Gap-Intervall: [High(i-2), Low(i)]
	•	Bearish FVG liegt vor, wenn:
High(i) < Low(i-2)
Gap-Intervall: [High(i), Low(i-2)]

Gültigkeitsanforderung:
	•	Das FVG muss nach dem OB entstehen und in die Impulsphase fallen (innerhalb der ersten drei Folgekerzen).

Phase 4: Struktur-Check (BOS/MSS)
Der Impuls muss eine signifikante Struktur brechen.

Swing-Definition (Fraktal, verbindlich):
	•	Ein Swing High ist ein lokales Hoch, das höher ist als die Hochs der n Kerzen links und rechts.
	•	Ein Swing Low ist ein lokales Tief, das tiefer ist als die Tiefs der n Kerzen links und rechts.
	•	n = swing_fractal_n (Default: 2).

BOS-Regel (Close-basiert, verbindlich):
	•	Bullish BOS: Eine Impuls-Kerze schließt mit ihrem Close über dem letzten bestätigten Swing High.
	•	Bearish BOS: Eine Impuls-Kerze schließt mit ihrem Close unter dem letzten bestätigten Swing Low.

Wichtig: Docht-Durchstiche zählen nicht als BOS. Nur Close außerhalb der Struktur.

Phase 5: Zustands-Check (Mitigation State)
Nach erfolgreicher Validierung wird der OB als Zone mit Status geführt.

States:
	•	UNMITIGATED: Kein Preis hat die Zone seit Bestätigung berührt.
	•	MITIGATED: Preis hat die Zone mindestens einmal berührt (Zone Touch).
	•	INVALID: Zone wurde invalidiert (Definition unten).

Mitigation-Kriterium (verbindlich):
	•	MITIGATED, sobald eine nachfolgende Kerze einen Zone Touch hat:
High >= bottom und Low <= top

Invalidierungs-Kriterium (verbindlich):
	•	Bullish OB INVALID, sobald nach Bestätigung eine Kerze die Stop-Edge berührt/überschreitet:
Low <= bottom
	•	Bearish OB INVALID, sobald:
High >= top

Hinweis: Invalidierung ist konservativ als Wick-Kriterium definiert, da die Spezifikation “Stop Edge berührt” verlangt.

⸻

3.2 Zeitkonsistenz & Bestätigung (Look-Ahead-Bias-Vermeidung)

Da Swing-Bestätigung und BOS zeitabhängig sind, wird zwischen “Formation” und “Bestätigung” unterschieden.

Zeitpunkte pro OB:
	•	formed_at: Timestamp der OB-Kerze (Base Candle).
	•	confirmed_at: Timestamp, an dem alle Kriterien (Displacement, FVG, BOS) erstmals erfüllt und damit validiert sind.

Regel: Der Backtest und jede Statistik verwenden ausschließlich den Zustand, wie er zum jeweiligen Zeitpunkt verfügbar war. Ein OB darf erst ab confirmed_at als existierende Zone gelten.

⸻

3.3 Output-Format (Detektions-Ergebnis)

Die Detection Engine liefert eine Liste von Zonenobjekten, die mindestens folgende Struktur besitzt:

Entry/Stop-Kanten (verbindliche Default-Policy):
	•	Default entry_policy = Near-Edge Entry:
	•	Bullish: entry_edge = top
	•	Bearish: entry_edge = bottom
	•	Default stop_policy = Stop Edge Touch:
	•	Bullish: stop_edge = bottom
	•	Bearish: stop_edge = top

Volume Weight (optional, definieren statt “frei interpretieren”):
	•	volume_weight = Volume(impulse_phase) / SMA(Volume, 20)
wobei impulse_phase die ersten drei Kerzen nach OB umfasst. (Alternative Definition ist zulässig, muss aber fixiert sein.)

⸻

4. Modul B: Backtest-Umgebung (Statistik & Simulation)

4.1 Simulations-Logik (Zone-Anlaufen)

Der Backtest verarbeitet historische OHLCV-Daten und simuliert das Anlaufen von Orderblocks ab confirmed_at.

Einstieg (Entry):
	•	Einstieg erfolgt beim ersten Zone-Kontakt mit der entry_edge.
	•	Entry wird ausgelöst, sobald eine Kerze die Entry-Kante berührt:
	•	Bullish: Low <= entry_edge
	•	Bearish: High >= entry_edge

Stop / Invalidierung (Miss):
	•	Miss tritt ein, wenn die stop_edge vor dem Ziel berührt wird:
	•	Bullish: Low <= stop_edge
	•	Bearish: High >= stop_edge

Erfolg (Hit):
	•	Hit tritt ein, wenn vor Stop-Touch das definierte Ziel erreicht wird.

Zieldefinition (Default):
	•	target_distance = target_rr * (top - bottom)
	•	Bullish: target = entry_price + target_distance
	•	Bearish: target = entry_price - target_distance

Hinweis zur Fill-Logik:
	•	Für Statistik gilt entry_price = entry_edge (Limit-Touch-Annahme). Abweichende Fill-Modelle sind möglich, müssen aber als Policy in den Report.

⸻

4.2 Erwarteter Statistik-Report (Metriken)

Der Backtest liefert mindestens folgende Metriken, jeweils pro Timeframe und optional pro Filtergruppe (z. B. Volume Weight Quantile):
	1.	Hit-Rate

	•	hits / (hits + misses) pro Zeitraum und Timeframe

	2.	Drawdown-Präzision (Penetration Depth)
Misst, wie tief der Preis im Schnitt in den OB eindringt, bevor er dreht.

Definition (in % der Zone, 0..100):
	•	Bullish:
	•	penetration = (entry_edge - min_low_after_entry_before_exit) / (entry_edge - stop_edge)
	•	Bearish:
	•	penetration = (max_high_after_entry_before_exit - entry_edge) / (stop_edge - entry_edge)
	•	Clamping auf [0, 1] und Ausgabe in Prozent.

	3.	Haltedauer

	•	first_touch_ts - confirmed_at (Durchschnitt, Median, Verteilung)

	4.	Zusatzmetriken (empfohlen, aber optional)

	•	Anzahl OBs pro Zeiteinheit (Signal-Dichte)
	•	Anteil mitigated vs unmitigated vs invalid
	•	Performance nach Filter (z. B. top 25% volume_weight)

4.3.
Ergänze die OB-Detection-Engine um eine statistische Volumen-Prüfung. Berechne für jeden potenziellen Orderblock den Z-Score des Volumens im Vergleich zu den vorherigen 50 Kerzen.

Implementiere eine Filterfunktion, die nur OBs mit einem Z-Score > 2.0 als HIGH_CONVICTION_OB markiert. Dokumentiere die mathematische Herleitung im Code-Header und stelle sicher, dass die Backtest-Engine die Erfolgsquote nach Z-Score-Clustern aufschlüsselt.

Recherchiere diese Dokumente:

Jean-Philippe Bouchaud: „Trades, Quotes and Prices“ – Das Standardwerk für das Verständnis von Preis-Impact und institutionellem Handeln.

Rama Cont: „A Functional Central Limit Theorem for Lot Size in a Limit Order Book“ – Erklärt mathematisch, wie sich Order-Volumina verhalten.

Marcos López de Prado: Er gilt als der Guru für Machine Learning im Trading. Seine Bücher (z. B. „Advances in Financial Machine Learning“) erklären, wie man Muster wie Orderblocks wissenschaftlich korrekt testet, ohne sich selbst zu belügen (Overfitting).


5. Workflow-Anweisungen (Iterationsplan, ohne Implementierungsdetails)

Schritt 1: Grundlogik & Validierung mit synthetischen Daten (Iteration 1)

Scope:
	•	ATR-Berechnung, FVG-Erkennung, Swing-/BOS-Regeln als mathematische Basis
	•	Validierungs-Szenarien:
	•	“Perfect OB” (muss erkannt werden)
	•	“Noise / False Signals” (muss verworfen werden)

Review-Schwerpunkt:
	•	Numerische Stabilität, deterministische Regeln, reproduzierbares Ergebnis

Schritt 2: Historischer Datencheck (Iteration 2)

Scope:
	•	Verarbeitung von mindestens 6 Monaten BTC/EUR Spot-Daten
	•	Erzeugung vollständiger Liste von UNMITIGATED / MITIGATED / INVALID Orderblocks mit Zeitkonsistenz (confirmed_at)

Review-Schwerpunkt:
	•	Datenintegrität, Laufzeit/Skalierung, korrekte State-Transitions

Schritt 3: Backtest, Filter & Reporting (Iteration 3)

Scope:
	•	Backtest über den historischen Datenbereich
	•	Report inkl. Trefferquoten und Segmentierung (z. B. Volume Weight Filter)

Qualitätsgate:
	•	Nachweis: Kein Look-Ahead-Bias (OB existiert erst ab confirmed_at; Swings werden erst nach Bestätigung genutzt)

⸻

6. Abnahme-Kriterien

Die Lösung gilt als abgenommen, wenn:
	1.	Modulstruktur klar getrennt ist (Detection, Backtest, Provider, Domain-Modelle).
	2.	Jede Regel in dieser Spezifikation deterministisch umgesetzt ist und im Output auditierbar wiedergegeben wird (inkl. Parameter & Referenzlevels).
	3.	Testabdeckung > 90% und Integrationstest über realistische Datenbasis vorhanden.
	4.	Output besteht aus:
	•	Validierter Liste von Preiszonen inkl. State (UNMITIGATED/MITIGATED/INVALID) und Zeitpunkten (formed_at/confirmed_at)
	•	Statistischer Auswertung der historischen Performance (Hit-Rate, Penetration, Haltedauer), inkl. Filter-Breakdowns
