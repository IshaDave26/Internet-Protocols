import os
import pandas as pd
import glob

def aggregate_results():
    """Aggregate results from individual leecher files into combined files"""
    print("Aggregating results from individual files...")
    
    # Find all individual result files
    result_files = glob.glob('results/*.csv')
    
    if not result_files:
        print("No result files found!")
        return
    
    # Create a combined DataFrame
    dfs = []
    for file in result_files:
        try:
            df = pd.read_csv(file)
            dfs.append(df)
        except Exception as e:
            print(f"Error reading {file}: {e}")
    
    if not dfs:
        print("No valid data found in result files!")
        return
    
    # Combine all DataFrames
    combined_df = pd.concat(dfs, ignore_index=True)
    
    # Save the combined results
    combined_df.to_csv('results/all_leechers_results.csv', index=False)
    print(f"Combined results saved to results/all_leechers_results.csv")
    
    # Create aggregated results by leecher and size category
    grouped = combined_df.groupby(['Leecher ID', 'Size Category'])
    
    # Calculate statistics for each group
    stats = grouped.agg({
        'Transfer Time': ['mean', 'std', 'min', 'max'],
        'Throughput': ['mean', 'std', 'min', 'max'],
        'Transfer Ratio': ['mean', 'std', 'min', 'max']
    }).reset_index()
    
    # Save the analysis
    stats.to_csv('results/leechers_performance_comparison.csv', index=False)
    print(f"Leecher performance comparison saved to results/leechers_performance_comparison.csv")
    
    # Create a summary with averages across all leechers
    summary = combined_df.groupby('Size Category').agg({
        'Transfer Time': ['mean', 'std'],
        'Throughput': ['mean', 'std'],
        'Transfer Ratio': ['mean', 'std']
    }).reset_index()
    
    summary.to_csv('results/all_leechers_summary.csv', index=False)
    print(f"Summary across all leechers saved to results/all_leechers_summary.csv")

if __name__ == "__main__":
    aggregate_results() 