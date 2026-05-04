from shiny import App, ui, reactive, Session, render
from shinywidgets import output_widget, render_widget
import plotly.graph_objects as go
import pandas as pd
import string
import re

# 1. UI (The Front-End Layout)
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.div(
            ui.h3("1536-Well Setup"),
            ui.input_text("plate_name", "Plate Title:", value="1536-Well Plate: PrP Compounds"),
            ui.input_numeric("assay_vol", "Assay Volume per Well (µL):", value=5.0, step=0.5),
            
            ui.input_radio_buttons(
                "readout", 
                "Select Readout Type:", 
                {"multiplex": "CTF + HiBiT (Multiplex)", "glo": "CellTiter-Glo (Single)"}
            ),
            ui.hr(),
            
            ui.h4("Assign Plate Blocks"),
            ui.input_text("condition", "Well Condition:", placeholder="e.g., Y-320, U251-MG..."),
            ui.input_text_area("notes", "Block Notes (Optional):", placeholder="e.g., NCGC00371126, 10mM stock..."),
            
            ui.input_text("start_well", "Start Well (e.g., A1)", placeholder="A1"),
            ui.input_text("end_well", "End Well (e.g., P24)", placeholder="P24"),
            
            ui.input_action_button("assign_btn", "Assign Block", class_="btn-primary", style="width: 100%; margin-bottom: 5px;"),
            ui.input_action_button("erase_btn", "Erase Block", class_="btn-warning", style="width: 100%; margin-bottom: 5px;"),
            ui.input_action_button("clear_btn", "Clear Entire Plate", class_="btn-danger", style="width: 100%;"),
            
            ui.hr(),
            
            ui.h4("Export Options"),
            ui.tags.button("📄 Export as PDF", onclick="window.print();", class_="btn btn-info", style="width: 100%; margin-bottom: 10px; font-weight: bold;"),
            ui.download_button("export_csv", "📊 Export Plate Data (CSV)", class_="btn-success", style="width: 100%; font-weight: bold;"),
            
            ui.hr(),
            class_="no-print"
        ),
        
        ui.h4("Reagent Master Mix"),
        ui.output_text_verbatim("volume_calc"), 
        ui.help_text(ui.tags.em("Note: Calculated volumes account for 10% dead volume and priming."))
    ),
    
    ui.tags.head(
        ui.tags.style("""
            .table th, .table td { text-align: left !important; padding-left: 10px !important; }
            
            @media print {
                @page { size: landscape; margin: 0.2in; }
                .no-print { display: none !important; }
                .bslib-sidebar-layout { display: block !important; }
                .card { zoom: 0.55 !important; }
                .js-plotly-plot, .plotly, .plot-container { width: 100% !important; max-width: 100% !important; }
                .bslib-sidebar-layout > aside { position: relative !important; width: 100% !important; border: none !important; padding: 0 !important; margin-bottom: 20px !important; }
                .bslib-sidebar-layout > .main { display: block !important; width: 100% !important; padding: 0 !important; }
                .card { border: none !important; box-shadow: none !important; }
                * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
                .table { page-break-inside: avoid; }
            }
        """)
    ),
    
    ui.card(
        ui.output_ui("dynamic_title"),
        ui.p("Click and drag to select wells. The Start and End boxes will auto-fill!", class_="no-print"),
        output_widget("plate_plot"),
        ui.hr(),
        ui.h4("Plate Legend & Notes"),
        
        # Swapped to UI Output so we can inject the raw HTML colored circles
        ui.output_ui("legend_table"),
        
        # The subtle, discreet signature
        ui.div(
            "Made by Colin Gordy", 
            style="text-align: right; font-size: 11px; color: #9CA3AF; margin-top: 40px; font-style: italic;"
        )
    )
)

# 2. Server (The Logic)
def server(input, output, session: Session):
    
    @render.ui
    def dynamic_title():
        return ui.h3(input.plate_name())

    plate_state = reactive.Value({}) 
    color_map = reactive.Value({"empty": "#E5E7EB"})
    
    palette = [
        "#115e59", "#3b82f6", "#ef4444", "#d946ef", "#f59e0b", "#10b981", 
        "#8b5cf6", "#fca5a5", "#0284c7", "#b91c1c", "#4d7c0f", "#c026d3", 
        "#ea580c", "#0d9488", "#4338ca", "#be123c", "#ca8a04", "#1d4ed8", 
        "#15803d", "#7e22ce", "#b45309", "#0f766e", "#6b21a8", "#9f1239"
    ]

    letters = list(string.ascii_uppercase)
    all_rows = letters + ['A' + l for l in letters[:6]]

    def handle_selection(trace, points, selector):
        if points.xs and points.ys:
            min_x, max_x = min(points.xs), max(points.xs)
            min_y, max_y = min(points.ys), max(points.ys)
            start_row_letter = all_rows[32 - int(max_y)]
            end_row_letter = all_rows[32 - int(min_y)]
            start_coord = f"{start_row_letter}{int(min_x)}"
            end_coord = f"{end_row_letter}{int(max_x)}"
            ui.update_text("start_well", value=start_coord, session=session)
            ui.update_text("end_well", value=end_coord, session=session)

    @reactive.Effect
    @reactive.event(input.assign_btn)
    def update_plate():
        start = input.start_well().upper().strip()
        end = input.end_well().upper().strip()
        cond = input.condition().strip()
        notes = input.notes().strip()
        
        if not cond:
            cond = "Unnamed"

        current_colors = color_map.get().copy()
        if cond not in current_colors:
            color_index = (len(current_colors) - 1) % len(palette)
            current_colors[cond] = palette[color_index]
            color_map.set(current_colors)

        match_start = re.match(r"([A-Z]+)(\d+)", start)
        match_end = re.match(r"([A-Z]+)(\d+)", end)

        if match_start and match_end:
            r1, c1 = match_start.groups()
            r2, c2 = match_end.groups()
            if r1 in all_rows and r2 in all_rows:
                r1_idx = all_rows.index(r1)
                r2_idx = all_rows.index(r2)
                c1_idx = int(c1)
                c2_idx = int(c2)
                min_r, max_r = min(r1_idx, r2_idx), max(r1_idx, r2_idx)
                min_c, max_c = min(c1_idx, c2_idx), max(c1_idx, c2_idx)

                current_state = plate_state.get().copy()
                for r in range(min_r, max_r + 1):
                    for c in range(min_c, max_c + 1):
                        well_id = f"{all_rows[r]}{c}"
                        current_state[well_id] = (cond, notes) 
                plate_state.set(current_state)

    @reactive.Effect
    @reactive.event(input.erase_btn)
    def erase_block():
        start = input.start_well().upper().strip()
        end = input.end_well().upper().strip()
        match_start = re.match(r"([A-Z]+)(\d+)", start)
        match_end = re.match(r"([A-Z]+)(\d+)", end)
        if match_start and match_end:
            r1, c1 = match_start.groups()
            r2, c2 = match_end.groups()
            if r1 in all_rows and r2 in all_rows:
                r1_idx = all_rows.index(r1)
                r2_idx = all_rows.index(r2)
                c1_idx = int(c1)
                c2_idx = int(c2)
                min_r, max_r = min(r1_idx, r2_idx), max(r1_idx, r2_idx)
                min_c, max_c = min(c1_idx, c2_idx), max(c1_idx, c2_idx)
                current_state = plate_state.get().copy()
                for r in range(min_r, max_r + 1):
                    for c in range(min_c, max_c + 1):
                        well_id = f"{all_rows[r]}{c}"
                        current_state[well_id] = ("empty", "")
                plate_state.set(current_state)

    @reactive.Effect
    @reactive.event(input.clear_btn)
    def clear_plate():
        plate_state.set({}) 

    @render.text
    def volume_calc():
        current_state = plate_state.get()
        assigned_wells = sum(1 for data in current_state.values() if data[0] != "empty")
        
        if assigned_wells == 0:
            return "Awaiting plate assignments..."
            
        calc_wells = assigned_wells * 1.10
        readout = input.readout()
        assay_v = input.assay_vol() 
        
        if readout == "glo":
            ctg_per_well = assay_v * 0.6
            total_ctg_ul = calc_wells * ctg_per_well
            total_ctg_ml = total_ctg_ul / 1000
            
            return (f"--- CellTiter-Glo (Single) ---\n"
                    f"Active Wells: {assigned_wells}\n"
                    f"Calculated Wells (+10%): {int(calc_wells)}\n"
                    f"Addition per well: {ctg_per_well:.2f} µL\n\n"
                    f"[CTG Reagent Needed]\n"
                    f"Volume: {total_ctg_ul:.1f} µL ({total_ctg_ml:.3f} mL)")
        else:
            ctf_per_well = assay_v / 5.0
            total_ctf_ul = calc_wells * ctf_per_well
            ctf_substrate_ul = total_ctf_ul * (10 / 2010)
            ctf_buffer_ml = (total_ctf_ul - ctf_substrate_ul) / 1000
            
            hibit_per_well = assay_v * 1.0
            total_hibit_ul = calc_wells * hibit_per_well
            total_hibit_ml = total_hibit_ul / 1000
            
            return (f"--- CTF + HiBiT (Multiplex) ---\n"
                    f"Active Wells: {assigned_wells}\n"
                    f"Calculated Wells (+10%): {int(calc_wells)}\n\n"
                    f"[1] CellTiter-Fluor ({ctf_per_well:.2f} µL/well)\n"
                    f" - Buffer: {ctf_buffer_ml:.3f} mL\n"
                    f" - Substrate: {ctf_substrate_ul:.2f} µL\n"
                    f" - Total CTF Mix: {total_ctf_ul:.1f} µL\n\n"
                    f"[2] HiBiT Reagent ({hibit_per_well:.2f} µL/well)\n"
                    f" - Total HiBiT: {total_hibit_ul:.1f} µL ({total_hibit_ml:.3f} mL)")

    @render_widget
    def plate_plot():
        current_state = plate_state.get()
        current_colors = color_map.get()
        x_vals, y_vals, colors, hover_texts = [], [], [], []
        
        for y_idx in range(32, 0, -1): 
            row_letter = all_rows[32 - y_idx]
            for x in range(1, 49):
                well_id = f"{row_letter}{x}"
                cond_data = current_state.get(well_id, ("empty", ""))
                condition = cond_data[0]
                notes = cond_data[1]
                
                x_vals.append(x)
                y_vals.append(y_idx)
                colors.append(current_colors.get(condition, "#E5E7EB"))
                
                if condition == "empty":
                    hover_texts.append(well_id)
                else:
                    hover_text = f"<b>{well_id}: {condition}</b>"
                    if notes:
                        hover_text += f"<br><i>{notes}</i>"
                    hover_texts.append(hover_text)
                
        fig = go.FigureWidget(data=go.Scatter(
            x=x_vals, y=y_vals, mode='markers',
            marker=dict(size=8, color=colors, line=dict(width=1, color='#9CA3AF')),
            hoverinfo='text', text=hover_texts 
        ))
        
        fig.update_layout(
            xaxis=dict(
                tickmode='array', 
                tickvals=list(range(1, 49)), 
                ticktext=[str(i) for i in range(1, 49)], 
                side='top', 
                tickangle=0, 
                tickfont=dict(size=10)
            ),
            yaxis=dict(
                tickmode='array', 
                tickvals=list(range(32, 0, -1)), 
                ticktext=all_rows,
                scaleanchor="x", 
                scaleratio=1
            ),
            width=1100,  # Forces the plate to stay wide
            height=700,  # Forces the height
            plot_bgcolor='white', 
            margin=dict(l=50, r=50, t=80, b=50), 
            dragmode="select" 
        )
        fig.update_yaxes(scaleanchor="x", scaleratio=1)
        fig.data[0].on_selection(handle_selection)
        return fig

    # The upgraded HTML Table Generator
    @render.ui
    def legend_table():
        state = plate_state.get()
        current_colors = color_map.get()
        summary = {}
        
        for well, (cond, notes) in state.items():
            if cond != "empty":
                if cond not in summary:
                    summary[cond] = {"Condition": cond, "Notes": notes, "_wells": []}
                summary[cond]["_wells"].append(well)
                
        if not summary:
            return ui.HTML("<table class='table'><tbody><tr><td style='color: #6B7280;'>No blocks assigned yet.</td></tr></tbody></table>")
            
        html = "<table class='table' style='width: 100%; border-collapse: collapse;'>"
        html += "<thead><tr style='border-bottom: 2px solid #E5E7EB;'><th style='width: 60px;'>Color</th><th>Condition</th><th>Notes</th><th>Assigned Wells</th></tr></thead>"
        html += "<tbody>"
        
        for cond, data in summary.items():
            wells = data["_wells"]
            rows, cols = [], []
            
            for w in wells:
                match = re.match(r"([A-Z]+)(\d+)", w)
                if match:
                    r, c = match.groups()
                    rows.append(all_rows.index(r))
                    cols.append(int(c))
            
            min_r, max_r = min(rows), max(rows)
            min_c, max_c = min(cols), max(cols)
            
            start_well = f"{all_rows[min_r]}{min_c}"
            end_well = f"{all_rows[max_r]}{max_c}"
            
            if start_well == end_well:
                well_display = f"{start_well} (1)"
            else:
                well_display = f"{start_well}-{end_well} ({len(wells)})"
                
            # Render the tiny physical color circle
            hex_color = current_colors.get(cond, "#E5E7EB")
            circle_html = f"<div style='width: 16px; height: 16px; border-radius: 50%; background-color: {hex_color}; border: 1px solid #9CA3AF;'></div>"
            
            html += f"<tr style='border-bottom: 1px solid #E5E7EB;'><td style='vertical-align: middle;'>{circle_html}</td><td style='vertical-align: middle; font-weight: 500;'>{cond}</td><td style='vertical-align: middle;'>{data['Notes']}</td><td style='vertical-align: middle;'>{well_display}</td></tr>"
            
        html += "</tbody></table>"
        
        return ui.HTML(html)

    @render.download(filename=lambda: f"{input.plate_name().replace(' ', '_')}.csv")
    def export_csv():
        state = plate_state.get()
        data = []
        for r in all_rows:
            for c in range(1, 49):
                well_id = f"{r}{c}"
                cond, notes = state.get(well_id, ("empty", ""))
                data.append({"Well": well_id, "Condition": cond, "Notes": notes})
        df = pd.DataFrame(data)
        yield df.to_csv(index=False).encode('utf-8')

app = App(app_ui, server)