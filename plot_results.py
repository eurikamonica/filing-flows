"""Standalone measured development chart. Created by ChatGPT (OpenAI)."""
from protocol import RUN, read


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    before=read(RUN/'baseline.json');after=read(RUN/'candidate.json')
    if before['status']!='completed' or after['status']!='completed':
        raise RuntimeError('Plot requires two completed fixed-development evaluations')
    figure,axes=plt.subplots(2,1,figsize=(12,12))
    for axis,regression in zip(axes,[False,True]):
        tasks=[task for task in before['tasks'] if task.startswith('regression:')==regression]
        positions=list(range(len(tasks)))
        axis.barh([i-.18 for i in positions],[before['tasks'][t]['correct']/before['tasks'][t]['rows'] for t in tasks],height=.35,label='Starting champion')
        axis.barh([i+.18 for i in positions],[after['tasks'][t]['correct']/after['tasks'][t]['rows'] for t in tasks],height=.35,label='Continued candidate')
        axis.set_yticks(positions,[t.removeprefix('regression:')+(' (invalid v1 contract)' if t=='basic_instruction' else '') for t in tasks]);axis.set_xlim(0,1)
        axis.set_xlabel('Joint correct / questions (including required source IDs)')
        axis.set_title('Historical validation regression: 2 questions/task' if regression else 'New development pilot: 3 questions/task')
        axis.legend()
    figure.suptitle('Engineering diagnostics: v1 contract defects; candidate not approved\nSealed final test not evaluated')
    figure.text(.99,.005,'Created by ChatGPT (OpenAI). Small samples and underspecified v1 contracts; not a capability-improvement claim.',ha='right',fontsize=8)
    figure.tight_layout(rect=[0,.02,1,.97])
    figure.savefig(RUN/'DEV_COMPARISON.png',dpi=150);figure.savefig(RUN/'DEV_COMPARISON.svg');plt.close(figure)


if __name__=='__main__':main()
