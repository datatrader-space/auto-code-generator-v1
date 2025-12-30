# -----------------------------------------------------------------------------
# File: backend/strategies/serializers.py
#
# Django REST Framework serializers to convert model instances to JSON.
# -----------------------------------------------------------------------------
from rest_framework import serializers
from .models import Demographic, Domain, Tool, KPI, Strategy, StrategyKPI

class DemographicSerializer(serializers.ModelSerializer):
    """Serializes the Demographic model."""
    class Meta:
        model = Demographic
        fields = '__all__'

class DomainSerializer(serializers.ModelSerializer):
    """Serializes the Domain model."""
    class Meta:
        model = Domain
        fields = '__all__'

class ToolSerializer(serializers.ModelSerializer):
    """Serializes the Tool model."""
    class Meta:
        model = Tool
        fields = '__all__'

class KPISerializer(serializers.ModelSerializer):
    """Serializes the KPI model."""
    class Meta:
        model = KPI
        fields = '__all__'

class SuperStrategyTypeSerializer(serializers.Serializer):
    """Serializes the hardcoded SuperStrategyType data."""
    name = serializers.CharField()

class StrategyStatusSerializer(serializers.Serializer):
    """Serializes the hardcoded StrategyStatus data."""
    name = serializers.CharField()

class StrategyKPISerializer(serializers.ModelSerializer):
    """Serializes the StrategyKPI intermediate model."""
    kpi_name = serializers.CharField(source='kpi.name', read_only=True)
    kpi_unit = serializers.CharField(source='kpi.unit', read_only=True)
    id = serializers.IntegerField(source='kpi.id', read_only=True) # Expose KPI ID

    class Meta:
        model = StrategyKPI
        fields = ['id', 'kpi_name', 'kpi_unit', 'target_value', 'timeline']
        extra_kwargs = {
            'target_value': {'required': True},
            'timeline': {'required': True},
        }

class StrategyDetailSerializer(serializers.ModelSerializer):
    """
    Serializes the Strategy model for detail view.
    It includes nested serializers for related objects.
    """
    demographics = DemographicSerializer(many=True, read_only=True)
    tools = ToolSerializer(many=True, read_only=True)
    domain_name = serializers.CharField(source='domain.name', read_only=True)
    kpis = StrategyKPISerializer(many=True, read_only=True)

    class Meta:
        model = Strategy
        fields = [
            'id', 'strategy_name', 'parent_strategy','super_strategy_type', 'domain', 'domain_name',
            'target_audience', 'description', 'budget', 'status',
            'demographics', 'tools', 'kpis'
        ]

class StrategyListSerializer(serializers.ModelSerializer):
    """
    Serializes the Strategy model for list view.
    This serializer is more concise for the list view.
    """
    domain_name = serializers.CharField(source='domain.name', read_only=True)

    class Meta:
        model = Strategy
        fields = [
            'id', 'strategy_name', 'parent_strategy','super_strategy_type', 'domain_name',
            'target_audience', 'status','kpis','description','tools'
        ]

class StrategyCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating a Strategy.
    This serializer accepts related object IDs and nested KPI data.
    """
    demographicIds = serializers.PrimaryKeyRelatedField(
        many=True,
        source='demographics',
        queryset=Demographic.objects.all()
    )
    toolIds = serializers.PrimaryKeyRelatedField(
        many=True,
        source='tools',
        queryset=Tool.objects.all()
    )
   

    class Meta:
        model = Strategy
        fields = [
            'strategy_name', 'parent_strategy','super_strategy_type', 'domain', 'target_audience',
            'description', 'budget', 'status', 'demographicIds', 'toolIds', 'kpis','id'
        ]

    def create(self, validated_data):
        demographics_data = validated_data.pop('demographics', [])

        tools_data = validated_data.pop('tools', [])
        
        print(validated_data)
        strategy = Strategy.objects.create(**validated_data)
       
        strategy.tools.set(tools_data)
        strategy.demographics.set(demographics_data)
        selected_kpis_data = validated_data.pop('kpis', [])
        for kpi_data in selected_kpis_data:
            # Assuming kpi.id is passed from the frontend, extract the ID
            kpi_id = kpi_data.get('id')
            if kpi_id:
                StrategyKPI.objects.create(
                    strategy=strategy,
                    kpi_id=kpi_id,
                    target_value=kpi_data.get('target_value'),
                    timeline=kpi_data.get('timeline')
                )
        return strategy

    def update(self, instance, validated_data):
        print(validated_data)
        demographics_data = validated_data.pop('demographics', [])
        tools_data = validated_data.pop('tools', [])
        

        # Update simple fields
        for attr, value in validated_data.items():
            print(attr)
            print(value)
            setattr(instance, attr, value)
        instance.save()

        # Update many-to-many relationships
        print(demographics_data)
        instance.demographics.set(demographics_data)
        instance.tools.set(tools_data)

        # Update nested StrategyKPIs
        selected_kpis_data = validated_data.pop('kpis', [])
        instance.selected_kpis.all().delete() # Easiest way to handle updates is to delete and recreate
        for kpi_data in selected_kpis_data:
            kpi_id = kpi_data.get('id')
            if kpi_id:
                StrategyKPI.objects.create(
                    strategy=instance,
                    kpi_id=kpi_id,
                    target_value=kpi_data.get('target_value'),
                    timeline=kpi_data.get('timeline')
                )

        return instance
